/* SPDX-License-Identifier: BSD-2-Clause
 *
 * LitePCIe driver
 *
 * This file is part of LitePCIe.
 *
 * Copyright (C) 2018-2023 / EnjoyDigital  / florent@enjoy-digital.fr
 *
 */

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/types.h>
#include <linux/ioctl.h>
#include <linux/init.h>
#include <linux/errno.h>
#include <linux/mm.h>
#include <linux/fs.h>
#include <linux/mmtimer.h>
#include <linux/miscdevice.h>
#include <linux/posix-timers.h>
#include <linux/interrupt.h>
#include <linux/time.h>
#include <linux/math64.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/pci.h>
#include <linux/pci_regs.h>
#include <linux/delay.h>
#include <linux/wait.h>
#include <linux/log2.h>
#include <linux/poll.h>
#include <linux/cdev.h>
#include <linux/platform_device.h>
#include <linux/version.h>
#include <linux/ptp_clock_kernel.h>

#include "litepcie.h"
#include "csr.h"
#include "config.h"
#include "flags.h"
#include "soc.h"

//#define DEBUG_CSR
//#define DEBUG_MSI
//#define DEBUG_POLL
//#define DEBUG_READ
//#define DEBUG_WRITE

#define LITEPCIE_NAME "litepcie"
#define LITEPCIE_MINOR_COUNT 32

#ifndef CSR_BASE
#define CSR_BASE 0x00000000
#endif

struct litepcie_dma_chan {
	uint32_t base;
	uint32_t writer_interrupt;
	uint32_t reader_interrupt;
	dma_addr_t reader_handle[DMA_BUFFER_COUNT];
	dma_addr_t writer_handle[DMA_BUFFER_COUNT];
	uint32_t *reader_addr[DMA_BUFFER_COUNT];
	uint32_t *writer_addr[DMA_BUFFER_COUNT];
	int64_t reader_hw_count;
	int64_t reader_hw_count_last;
	int64_t reader_sw_count;
	int64_t writer_hw_count;
	int64_t writer_hw_count_last;
	int64_t writer_sw_count;
	uint8_t writer_enable;
	uint8_t reader_enable;
	uint8_t writer_lock;
	uint8_t reader_lock;
};

struct litepcie_chan {
	struct litepcie_device *litepcie_dev;
	struct litepcie_dma_chan dma;
	struct cdev cdev;
	uint32_t block_size;
	uint32_t core_base;
	wait_queue_head_t wait_rd; /* to wait for an ongoing read */
	wait_queue_head_t wait_wr; /* to wait for an ongoing write */

	int index;
	int minor;
};

struct litepcie_device {
	struct pci_dev *dev;
	struct platform_device *uart;
	resource_size_t bar0_size;
	phys_addr_t bar0_phys_addr;
	uint8_t *bar0_addr; /* virtual address of BAR0 */
	struct litepcie_chan chan[DMA_CHANNEL_COUNT];
	spinlock_t lock;
	int minor_base;
	int irqs;
	int channels;
	/* System time value lock */
	spinlock_t tmreg_lock;
	struct ptp_clock *litepcie_ptp_clock;
	struct system_time_snapshot snapshot;
	struct ptp_clock_info ptp_caps;
};

struct litepcie_chan_priv {
	struct litepcie_chan *chan;
	bool reader;
	bool writer;
};


static int litepcie_major;
static int litepcie_minor_idx;
static struct class *litepcie_class;
static dev_t litepcie_dev_t;

static inline uint32_t litepcie_readl(struct litepcie_device *s, uint32_t addr)
{
	uint32_t val;

	val = readl(s->bar0_addr + addr - CSR_BASE);
#ifdef DEBUG_CSR
	dev_dbg(&s->dev->dev, "csr_read: 0x%08x @ 0x%08x", val, addr);
#endif
	return val;
}

static inline void litepcie_writel(struct litepcie_device *s, uint32_t addr, uint32_t val)
{
#ifdef DEBUG_CSR
	dev_dbg(&s->dev->dev, "csr_write: 0x%08x @ 0x%08x", val, addr);
#endif
	return writel(val, s->bar0_addr + addr - CSR_BASE);
}

static void litepcie_enable_interrupt(struct litepcie_device *s, int irq_num)
{
	uint32_t v;

	v = litepcie_readl(s, CSR_PCIE_MSI_ENABLE_ADDR);
	v |= (1 << irq_num);
	litepcie_writel(s, CSR_PCIE_MSI_ENABLE_ADDR, v);
}

static void litepcie_disable_interrupt(struct litepcie_device *s, int irq_num)
{
	uint32_t v;

	v = litepcie_readl(s, CSR_PCIE_MSI_ENABLE_ADDR);
	v &= ~(1 << irq_num);
	litepcie_writel(s, CSR_PCIE_MSI_ENABLE_ADDR, v);
}

static int litepcie_dma_init(struct litepcie_device *s)
{

	int i, j;
	struct litepcie_dma_chan *dmachan;

	if (!s)
		return -ENODEV;

	/* for each dma channel */
	for (i = 0; i < s->channels; i++) {
		dmachan = &s->chan[i].dma;
		/* for each dma buffer */
		for (j = 0; j < DMA_BUFFER_COUNT; j++) {
			/* allocate rd */
			dmachan->reader_addr[j] = dmam_alloc_coherent(
				&s->dev->dev,
				DMA_BUFFER_SIZE,
				&dmachan->reader_handle[j],
				GFP_KERNEL);
			/* allocate wr */
			dmachan->writer_addr[j] = dmam_alloc_coherent(
				&s->dev->dev,
				DMA_BUFFER_SIZE,
				&dmachan->writer_handle[j],
				GFP_KERNEL);
			/* check */
			if (!dmachan->writer_addr[j]
				|| !dmachan->reader_addr[j]) {
				dev_err(&s->dev->dev, "Failed to allocate dma buffers\n");
				return -ENOMEM;
			}
		}
	}

	return 0;
}

static void litepcie_dma_writer_start(struct litepcie_device *s, int chan_num)
{
	struct litepcie_dma_chan *dmachan;
	int i;

	dmachan = &s->chan[chan_num].dma;

	/* Fill DMA Writer descriptors. */
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_ENABLE_OFFSET, 0);
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_FLUSH_OFFSET, 1);
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_LOOP_PROG_N_OFFSET, 0);
	for (i = 0; i < DMA_BUFFER_COUNT; i++) {
		/* Fill buffer size + parameters. */
		litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_VALUE_OFFSET,
#ifndef DMA_BUFFER_ALIGNED
			DMA_LAST_DISABLE |
#endif
			(!(i%DMA_BUFFER_PER_IRQ == 0)) * DMA_IRQ_DISABLE | /* generate an msi */
			DMA_BUFFER_SIZE);                                  /* every n buffers */
		/* Fill 32-bit Address LSB. */
		litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_VALUE_OFFSET + 4, (dmachan->writer_handle[i] >>  0) & 0xffffffff);
		/* Write descriptor (and fill 32-bit Address MSB for 64-bit mode). */
		litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_WE_OFFSET,        (dmachan->writer_handle[i] >> 32) & 0xffffffff);
	}
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_LOOP_PROG_N_OFFSET, 1);

	/* Clear counters. */
	dmachan->writer_hw_count = 0;
	dmachan->writer_hw_count_last = 0;
	dmachan->writer_sw_count = 0;

	/* Start DMA Writer. */
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_ENABLE_OFFSET, 1);
}

static void litepcie_dma_writer_stop(struct litepcie_device *s, int chan_num)
{
	struct litepcie_dma_chan *dmachan;

	dmachan = &s->chan[chan_num].dma;

	/* Flush and stop DMA Writer. */
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_LOOP_PROG_N_OFFSET, 0);
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_FLUSH_OFFSET, 1);
	udelay(1000);
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_ENABLE_OFFSET, 0);
	litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_TABLE_FLUSH_OFFSET, 1);

	/* Clear counters. */
	dmachan->writer_hw_count = 0;
	dmachan->writer_hw_count_last = 0;
	dmachan->writer_sw_count = 0;
}

static void litepcie_dma_reader_start(struct litepcie_device *s, int chan_num)
{
	struct litepcie_dma_chan *dmachan;
	int i;

	dmachan = &s->chan[chan_num].dma;

	/* Fill DMA Reader descriptors. */
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_ENABLE_OFFSET, 0);
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_FLUSH_OFFSET, 1);
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_LOOP_PROG_N_OFFSET, 0);
	for (i = 0; i < DMA_BUFFER_COUNT; i++) {
		/* Fill buffer size + parameters. */
		litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_VALUE_OFFSET,
#ifndef DMA_BUFFER_ALIGNED
			DMA_LAST_DISABLE |
#endif
			(!(i%DMA_BUFFER_PER_IRQ == 0)) * DMA_IRQ_DISABLE | /* generate an msi */
			DMA_BUFFER_SIZE);                                  /* every n buffers */
		/* Fill 32-bit Address LSB. */
		litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_VALUE_OFFSET + 4, (dmachan->reader_handle[i] >>  0) & 0xffffffff);
		/* Write descriptor (and fill 32-bit Address MSB for 64-bit mode). */
		litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_WE_OFFSET, (dmachan->reader_handle[i] >> 32) & 0xffffffff);
	}
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_LOOP_PROG_N_OFFSET, 1);

	/* clear counters */
	dmachan->reader_hw_count = 0;
	dmachan->reader_hw_count_last = 0;
	dmachan->reader_sw_count = 0;

	/* start dma reader */
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_ENABLE_OFFSET, 1);
}

static void litepcie_dma_reader_stop(struct litepcie_device *s, int chan_num)
{
	struct litepcie_dma_chan *dmachan;

	dmachan = &s->chan[chan_num].dma;

	/* flush and stop dma reader */
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_LOOP_PROG_N_OFFSET, 0);
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_FLUSH_OFFSET, 1);
	udelay(1000);
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_ENABLE_OFFSET, 0);
	litepcie_writel(s, dmachan->base + PCIE_DMA_READER_TABLE_FLUSH_OFFSET, 1);

	/* clear counters */
	dmachan->reader_hw_count = 0;
	dmachan->reader_hw_count_last = 0;
	dmachan->reader_sw_count = 0;
}

void litepcie_stop_dma(struct litepcie_device *s)
{
	struct litepcie_dma_chan *dmachan;
	int i;

	for (i = 0; i < s->channels; i++) {
		dmachan = &s->chan[i].dma;
		litepcie_writel(s, dmachan->base + PCIE_DMA_WRITER_ENABLE_OFFSET, 0);
		litepcie_writel(s, dmachan->base + PCIE_DMA_READER_ENABLE_OFFSET, 0);
	}
}

static irqreturn_t litepcie_interrupt(int irq, void *data)
{
	struct litepcie_device *s = (struct litepcie_device *) data;
	struct litepcie_chan *chan;
	uint32_t loop_status;
	uint32_t clear_mask, irq_vector, irq_enable;
	int i;

/* Single MSI */
#ifdef CSR_PCIE_MSI_CLEAR_ADDR
	irq_vector = litepcie_readl(s, CSR_PCIE_MSI_VECTOR_ADDR);
	irq_enable = litepcie_readl(s, CSR_PCIE_MSI_ENABLE_ADDR);
/* MSI MultiVector / MSI-X */
#else
	irq_vector = 0;
	for (i = 0; i < s->irqs; i++) {
		if (irq == pci_irq_vector(s->dev, i)) {
			irq_vector = (1 << i);
			break;
		}
	}
	irq_enable = litepcie_readl(s, CSR_PCIE_MSI_ENABLE_ADDR);
#endif

#ifdef DEBUG_MSI
	dev_dbg(&s->dev->dev, "MSI: 0x%x 0x%x\n", irq_vector, irq_enable);
#endif
	irq_vector &= irq_enable;
	clear_mask = 0;

	for (i = 0; i < s->channels; i++) {
		chan = &s->chan[i];
		/* dma reader interrupt handling */
		if (irq_vector & (1 << chan->dma.reader_interrupt)) {
			loop_status = litepcie_readl(s, chan->dma.base +
				PCIE_DMA_READER_TABLE_LOOP_STATUS_OFFSET);
			chan->dma.reader_hw_count &= ((~(DMA_BUFFER_COUNT - 1) << 16) & 0xffffffffffff0000);
			chan->dma.reader_hw_count |= (loop_status >> 16) * DMA_BUFFER_COUNT + (loop_status & 0xffff);
			if (chan->dma.reader_hw_count_last > chan->dma.reader_hw_count)
				chan->dma.reader_hw_count += (1 << (ilog2(DMA_BUFFER_COUNT) + 16));
			chan->dma.reader_hw_count_last = chan->dma.reader_hw_count;
#ifdef DEBUG_MSI
			dev_dbg(&s->dev->dev, "MSI DMA%d Reader buf: %lld\n", i,
				chan->dma.reader_hw_count);
#endif
			wake_up_interruptible(&chan->wait_wr);
			clear_mask |= (1 << chan->dma.reader_interrupt);
		}
		/* dma writer interrupt handling */
		if (irq_vector & (1 << chan->dma.writer_interrupt)) {
			loop_status = litepcie_readl(s, chan->dma.base +
				PCIE_DMA_WRITER_TABLE_LOOP_STATUS_OFFSET);
			chan->dma.writer_hw_count &= ((~(DMA_BUFFER_COUNT - 1) << 16) & 0xffffffffffff0000);
			chan->dma.writer_hw_count |= (loop_status >> 16) * DMA_BUFFER_COUNT + (loop_status & 0xffff);
			if (chan->dma.writer_hw_count_last > chan->dma.writer_hw_count)
				chan->dma.writer_hw_count += (1 << (ilog2(DMA_BUFFER_COUNT) + 16));
			chan->dma.writer_hw_count_last = chan->dma.writer_hw_count;
#ifdef DEBUG_MSI
			dev_dbg(&s->dev->dev, "MSI DMA%d Writer buf: %lld\n", i,
				chan->dma.writer_hw_count);
#endif
			wake_up_interruptible(&chan->wait_rd);
			clear_mask |= (1 << chan->dma.writer_interrupt);
		}
	}

#ifdef CSR_PCIE_MSI_CLEAR_ADDR
	litepcie_writel(s, CSR_PCIE_MSI_CLEAR_ADDR, clear_mask);
#endif

	return IRQ_HANDLED;
}

static int litepcie_open(struct inode *inode, struct file *file)
{
	struct litepcie_chan *chan = container_of(inode->i_cdev, struct litepcie_chan, cdev);
	struct litepcie_chan_priv *chan_priv = kzalloc(sizeof(*chan_priv), GFP_KERNEL);

	if (!chan_priv)
		return -ENOMEM;

	chan_priv->chan = chan;
	file->private_data = chan_priv;

	if (chan->dma.reader_enable == 0) { /* clear only if disabled */
		chan->dma.reader_hw_count = 0;
		chan->dma.reader_hw_count_last = 0;
		chan->dma.reader_sw_count = 0;
	}

	if (chan->dma.writer_enable == 0) { /* clear only if disabled */
		chan->dma.writer_hw_count = 0;
		chan->dma.writer_hw_count_last = 0;
		chan->dma.writer_sw_count = 0;
	}

	return 0;
}

static int litepcie_release(struct inode *inode, struct file *file)
{
	struct litepcie_chan_priv *chan_priv = file->private_data;
	struct litepcie_chan *chan = chan_priv->chan;

	if (chan_priv->reader) {
		/* disable interrupt */
		litepcie_disable_interrupt(chan->litepcie_dev, chan->dma.reader_interrupt);
		/* disable DMA */
		litepcie_dma_reader_stop(chan->litepcie_dev, chan->index);
		chan->dma.reader_lock = 0;
		chan->dma.reader_enable = 0;
	}

	if (chan_priv->writer) {
		/* disable interrupt */
		litepcie_disable_interrupt(chan->litepcie_dev, chan->dma.writer_interrupt);
		/* disable DMA */
		litepcie_dma_writer_stop(chan->litepcie_dev, chan->index);
		chan->dma.writer_lock = 0;
		chan->dma.writer_enable = 0;
	}

	kfree(chan_priv);

	return 0;
}

static ssize_t litepcie_read(struct file *file, char __user *data, size_t size, loff_t *offset)
{
	size_t len;
	int i, ret;
	int overflows;

	struct litepcie_chan_priv *chan_priv = file->private_data;
	struct litepcie_chan *chan = chan_priv->chan;
	struct litepcie_device *s = chan->litepcie_dev;

	if (file->f_flags & O_NONBLOCK) {
		if (chan->dma.writer_hw_count == chan->dma.writer_sw_count)
			ret = -EAGAIN;
		else
			ret = 0;
	} else {
		ret = wait_event_interruptible(chan->wait_rd,
					       (chan->dma.writer_hw_count - chan->dma.writer_sw_count) > 0);
	}

	if (ret < 0)
		return ret;

	i = 0;
	overflows = 0;
	len = size;
	while (len >= DMA_BUFFER_SIZE) {
		if ((chan->dma.writer_hw_count - chan->dma.writer_sw_count) > 0) {
			if ((chan->dma.writer_hw_count - chan->dma.writer_sw_count) > DMA_BUFFER_COUNT/2) {
				overflows++;
			} else {
				ret = copy_to_user(data + (chan->block_size * i),
						   chan->dma.writer_addr[chan->dma.writer_sw_count%DMA_BUFFER_COUNT],
						   DMA_BUFFER_SIZE);
				if (ret)
					return -EFAULT;
			}
			len -= DMA_BUFFER_SIZE;
			chan->dma.writer_sw_count += 1;
			i++;
		} else {
			break;
		}
	}

	if (overflows)
		dev_err(&s->dev->dev, "Reading too late, %d buffers lost\n", overflows);

#ifdef DEBUG_READ
	dev_dbg(&s->dev->dev, "read: read %ld bytes out of %ld\n", size - len, size);
#endif

	return size - len;
}

static ssize_t litepcie_write(struct file *file, const char __user *data, size_t size, loff_t *offset)
{
	size_t len;
	int i, ret;
	int underflows;

	struct litepcie_chan_priv *chan_priv = file->private_data;
	struct litepcie_chan *chan = chan_priv->chan;
	struct litepcie_device *s = chan->litepcie_dev;

	if (file->f_flags & O_NONBLOCK) {
		if (chan->dma.reader_hw_count == chan->dma.reader_sw_count)
			ret = -EAGAIN;
		else
			ret = 0;
	} else {
		ret = wait_event_interruptible(chan->wait_wr,
					       (chan->dma.reader_sw_count - chan->dma.reader_hw_count) < DMA_BUFFER_COUNT/2);
	}

	if (ret < 0)
		return ret;

	i = 0;
	underflows = 0;
	len = size;
	while (len >= DMA_BUFFER_SIZE) {
		if ((chan->dma.reader_sw_count - chan->dma.reader_hw_count) < DMA_BUFFER_COUNT/2) {
			if ((chan->dma.reader_sw_count - chan->dma.reader_hw_count) < 0) {
				underflows++;
			} else {
				ret = copy_from_user(chan->dma.reader_addr[chan->dma.reader_sw_count%DMA_BUFFER_COUNT],
						     data + (chan->block_size * i), DMA_BUFFER_SIZE);
				if (ret)
					return -EFAULT;
			}
			len -= DMA_BUFFER_SIZE;
			chan->dma.reader_sw_count += 1;
			i++;
		} else {
			break;
		}
	}

	if (underflows)
		dev_err(&s->dev->dev, "Writing too late, %d buffers lost\n", underflows);

#ifdef DEBUG_WRITE
	dev_dbg(&s->dev->dev, "write: write %ld bytes out of %ld\n", size - len, size);
#endif

	return size - len;
}

static int litepcie_mmap(struct file *file, struct vm_area_struct *vma)
{
	struct litepcie_chan_priv *chan_priv = file->private_data;
	struct litepcie_chan *chan = chan_priv->chan;
	struct litepcie_device *s = chan->litepcie_dev;
	unsigned long pfn;
	int is_tx, i;

	if (vma->vm_end - vma->vm_start != DMA_BUFFER_TOTAL_SIZE)
		return -EINVAL;

	if (vma->vm_pgoff == 0)
		is_tx = 1;
	else if (vma->vm_pgoff == (DMA_BUFFER_TOTAL_SIZE >> PAGE_SHIFT))
		is_tx = 0;
	else
		return -EINVAL;

	for (i = 0; i < DMA_BUFFER_COUNT; i++) {
		if (is_tx)
			pfn = __pa(chan->dma.reader_addr[i]) >> PAGE_SHIFT;
		else
			pfn = __pa(chan->dma.writer_addr[i]) >> PAGE_SHIFT;
		/*
		 * Note: the memory is cached, so the user must explicitly
		 * flush the CPU caches on architectures which require it.
		 */
		if (remap_pfn_range(vma, vma->vm_start + i * DMA_BUFFER_SIZE, pfn,
				    DMA_BUFFER_SIZE, vma->vm_page_prot)) {
			dev_err(&s->dev->dev, "mmap remap_pfn_range failed\n");
			return -EAGAIN;
		}
	}

	return 0;
}

static unsigned int litepcie_poll(struct file *file, poll_table *wait)
{
	unsigned int mask = 0;

	struct litepcie_chan_priv *chan_priv = file->private_data;
	struct litepcie_chan *chan = chan_priv->chan;
#ifdef DEBUG_POLL
	struct litepcie_device *s = chan->litepcie_dev;
#endif

	poll_wait(file, &chan->wait_rd, wait);
	poll_wait(file, &chan->wait_wr, wait);

#ifdef DEBUG_POLL
	dev_dbg(&s->dev->dev, "poll: writer hw_count: %10lld / sw_count %10lld\n",
	chan->dma.writer_hw_count, chan->dma.writer_sw_count);
	dev_dbg(&s->dev->dev, "poll: reader hw_count: %10lld / sw_count %10lld\n",
	chan->dma.reader_hw_count, chan->dma.reader_sw_count);
#endif

	if ((chan->dma.writer_hw_count - chan->dma.writer_sw_count) > 2)
		mask |= POLLIN | POLLRDNORM;

	if ((chan->dma.reader_sw_count - chan->dma.reader_hw_count) < DMA_BUFFER_COUNT/2)
		mask |= POLLOUT | POLLWRNORM;

	return mask;
}

#ifdef CSR_FLASH_BASE
/* SPI */

#define SPI_TIMEOUT 100000 /* in us */

static int litepcie_flash_spi(struct litepcie_device *s, struct litepcie_ioctl_flash *m)
{
	int i;

	if (m->tx_len < 8 || m->tx_len > 40)
		return -EINVAL;

	litepcie_writel(s, CSR_FLASH_SPI_MOSI_ADDR, m->tx_data >> 32);
	litepcie_writel(s, CSR_FLASH_SPI_MOSI_ADDR + 4, m->tx_data);
	litepcie_writel(s, CSR_FLASH_SPI_CONTROL_ADDR,
		SPI_CTRL_START | (m->tx_len * SPI_CTRL_LENGTH));
	udelay(16);
	for (i = 0; i < SPI_TIMEOUT; i++) {
		if (litepcie_readl(s, CSR_FLASH_SPI_STATUS_ADDR) & SPI_STATUS_DONE)
			break;
		udelay(1);
	}
	m->rx_data = ((uint64_t)litepcie_readl(s, CSR_FLASH_SPI_MISO_ADDR) << 32) |
		litepcie_readl(s, CSR_FLASH_SPI_MISO_ADDR + 4);
	return 0;
}
#endif

static long litepcie_ioctl(struct file *file, unsigned int cmd,
			   unsigned long arg)
{
	long ret = 0;

	struct litepcie_chan_priv *chan_priv = file->private_data;
	struct litepcie_chan *chan = chan_priv->chan;
	struct litepcie_device *dev = chan->litepcie_dev;

	switch (cmd) {
	case LITEPCIE_IOCTL_REG:
	{
		struct litepcie_ioctl_reg m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}
		if (m.is_write)
			litepcie_writel(dev, m.addr, m.val);
		else
			m.val = litepcie_readl(dev, m.addr);

		if (copy_to_user((void *)arg, &m, sizeof(m))) {
			ret = -EFAULT;
			break;
		}
	}
	break;
#ifdef CSR_FLASH_BASE
	case LITEPCIE_IOCTL_FLASH:
	{
		struct litepcie_ioctl_flash m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}
		ret = litepcie_flash_spi(dev, &m);
		if (ret == 0) {
			if (copy_to_user((void *)arg, &m, sizeof(m))) {
				ret = -EFAULT;
				break;
			}
		}
	}
	break;
#endif
#ifdef CSR_ICAP_BASE
	case LITEPCIE_IOCTL_ICAP:
	{
		struct litepcie_ioctl_icap m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		litepcie_writel(dev, CSR_ICAP_ADDR_ADDR, m.addr);
		litepcie_writel(dev, CSR_ICAP_DATA_ADDR, m.data);
		litepcie_writel(dev, CSR_ICAP_WRITE_ADDR, 1);
	}
	break;
#endif
	case LITEPCIE_IOCTL_DMA:
	{
		struct litepcie_ioctl_dma m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		/* loopback */
		litepcie_writel(chan->litepcie_dev, chan->dma.base + PCIE_DMA_LOOPBACK_ENABLE_OFFSET, m.loopback_enable);
	}
	break;
	case LITEPCIE_IOCTL_DMA_WRITER:
	{
		struct litepcie_ioctl_dma_writer m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		if (m.enable != chan->dma.writer_enable) {
			/* enable / disable DMA */
			if (m.enable) {
				litepcie_dma_writer_start(chan->litepcie_dev, chan->index);
				litepcie_enable_interrupt(chan->litepcie_dev, chan->dma.writer_interrupt);
			} else {
				litepcie_disable_interrupt(chan->litepcie_dev, chan->dma.writer_interrupt);
				litepcie_dma_writer_stop(chan->litepcie_dev, chan->index);
			}

		}

		chan->dma.writer_enable = m.enable;

		m.hw_count = chan->dma.writer_hw_count;
		m.sw_count = chan->dma.writer_sw_count;

		if (copy_to_user((void *)arg, &m, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

	}
	break;
	case LITEPCIE_IOCTL_DMA_READER:
	{
		struct litepcie_ioctl_dma_reader m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		if (m.enable != chan->dma.reader_enable) {
			/* enable / disable DMA */
			if (m.enable) {
				litepcie_dma_reader_start(chan->litepcie_dev, chan->index);
				litepcie_enable_interrupt(chan->litepcie_dev, chan->dma.reader_interrupt);
			} else {
				litepcie_disable_interrupt(chan->litepcie_dev, chan->dma.reader_interrupt);
				litepcie_dma_reader_stop(chan->litepcie_dev, chan->index);
			}
		}

		chan->dma.reader_enable = m.enable;

		m.hw_count = chan->dma.reader_hw_count;
		m.sw_count = chan->dma.reader_sw_count;

		if (copy_to_user((void *)arg, &m, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

	}
	break;
	case LITEPCIE_IOCTL_MMAP_DMA_INFO:
	{
		struct litepcie_ioctl_mmap_dma_info m;

		m.dma_tx_buf_offset = 0;
		m.dma_tx_buf_size = DMA_BUFFER_SIZE;
		m.dma_tx_buf_count = DMA_BUFFER_COUNT;

		m.dma_rx_buf_offset = DMA_BUFFER_TOTAL_SIZE;
		m.dma_rx_buf_size = DMA_BUFFER_SIZE;
		m.dma_rx_buf_count = DMA_BUFFER_COUNT;

		if (copy_to_user((void *)arg, &m, sizeof(m))) {
			ret = -EFAULT;
			break;
		}
	}
	break;
	case LITEPCIE_IOCTL_MMAP_DMA_WRITER_UPDATE:
	{
		struct litepcie_ioctl_mmap_dma_update m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		chan->dma.writer_sw_count = m.sw_count;
	}
	break;
	case LITEPCIE_IOCTL_MMAP_DMA_READER_UPDATE:
	{
		struct litepcie_ioctl_mmap_dma_update m;

		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		chan->dma.reader_sw_count = m.sw_count;
	}
	break;
	case LITEPCIE_IOCTL_LOCK:
	{
		struct litepcie_ioctl_lock m;


		if (copy_from_user(&m, (void *)arg, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

		m.dma_reader_status = 1;
		if (m.dma_reader_request) {
			if (chan->dma.reader_lock) {
				m.dma_reader_status = 0;
			} else {
				chan->dma.reader_lock = 1;
				chan_priv->reader = 1;
			}
		}
		if (m.dma_reader_release) {
			chan->dma.reader_lock = 0;
			chan_priv->reader = 0;
		}

		m.dma_writer_status = 1;
		if (m.dma_writer_request) {
			if (chan->dma.writer_lock) {
				m.dma_writer_status = 0;
			} else {
				chan->dma.writer_lock = 1;
				chan_priv->writer = 1;
			}
		}
		if (m.dma_writer_release) {
			chan->dma.writer_lock = 0;
			chan_priv->writer = 0;
		}

		if (copy_to_user((void *)arg, &m, sizeof(m))) {
			ret = -EFAULT;
			break;
		}

	}
	break;
	default:
		ret = -ENOIOCTLCMD;
		break;
	}
	return ret;
}

static const struct file_operations litepcie_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = litepcie_ioctl,
	.open = litepcie_open,
	.release = litepcie_release,
	.read = litepcie_read,
	.poll = litepcie_poll,
	.write = litepcie_write,
	.mmap = litepcie_mmap,
};

static int litepcie_alloc_chdev(struct litepcie_device *s)
{
	int i, j;
	int ret;
	int index;

	index = litepcie_minor_idx;
	s->minor_base = litepcie_minor_idx;
	for (i = 0; i < s->channels; i++) {
		cdev_init(&s->chan[i].cdev, &litepcie_fops);
		ret = cdev_add(&s->chan[i].cdev, MKDEV(litepcie_major, index), 1);
		if (ret < 0) {
			dev_err(&s->dev->dev, "Failed to allocate cdev\n");
			goto fail_alloc;
		}
		index++;
	}

	index = litepcie_minor_idx;
	for (i = 0; i < s->channels; i++) {
		dev_info(&s->dev->dev, "Creating /dev/litepcie%d\n", index);
		if (!device_create(litepcie_class, NULL, MKDEV(litepcie_major, index), NULL, "litepcie%d", index)) {
			ret = -EINVAL;
			dev_err(&s->dev->dev, "Failed to create device\n");
			goto fail_create;
		}
		index++;

	}

	litepcie_minor_idx = index;
	return 0;

fail_create:
	index = litepcie_minor_idx;
	for (j = 0; j < i; j++)
		device_destroy(litepcie_class, MKDEV(litepcie_major, index++));

fail_alloc:
	for (i = 0; i < s->channels; i++)
		cdev_del(&s->chan[i].cdev);

	return ret;
}

static void litepcie_free_chdev(struct litepcie_device *s)
{
	int i;

	for (i = 0; i < s->channels; i++) {
		device_destroy(litepcie_class, MKDEV(litepcie_major, s->minor_base + i));
		cdev_del(&s->chan[i].cdev);
	}
}

/* from stackoverflow */
void sfind(char *string, char *format, ...)
{
	va_list arglist;

	va_start(arglist, format);
	vsscanf(string, format, arglist);
	va_end(arglist);
}

struct revision {
	int yy;
	int mm;
	int dd;
};

int compare_revisions(struct revision d1, struct revision d2)
{
	if (d1.yy < d2.yy)
		return -1;
	else if (d1.yy > d2.yy)
		return 1;

	if (d1.mm < d2.mm)
		return -1;
	else if (d1.mm > d2.mm)
		return 1;
	else if (d1.dd < d2.dd)
		return -1;
	else if (d1.dd > d2.dd)
		return 1;

	return 0;
}
/* from stackoverflow */

/* time */
#define TIME_CONTROL_ENABLE   (1 << CSR_TIME_CONTROLLER_CONTROL_ENABLE_OFFSET)
#define TIME_CONTROL_LATCH    (1 << CSR_TIME_CONTROLLER_CONTROL_LATCH_OFFSET)
#define TIME_CONTROL_OVERRIDE (1 << CSR_TIME_CONTROLLER_CONTROL_OVERRIDE_OFFSET)

/* PTM */
#define PTM_CONTROL_ENABLE  (1 << CSR_PTM_REQUESTER_CONTROL_ENABLE_OFFSET)
#define PTM_CONTROL_TRIGGER (1 << CSR_PTM_REQUESTER_CONTROL_TRIGGER_OFFSET)
#define PTM_STATUS_VALID    (1 << CSR_PTM_REQUESTER_STATUS_VALID_OFFSET)
/* t1 */
#define PTM_T1_TIME_L       (CSR_PTM_REQUESTER_T1_TIME_ADDR + (4))
#define PTM_T1_TIME_H       (CSR_PTM_REQUESTER_T1_TIME_ADDR + (0))
/* t2 */
#define PTM_MASTER_TIME_L   (CSR_PTM_REQUESTER_MASTER_TIME_ADDR + (4))
#define PTM_MASTER_TIME_H   (CSR_PTM_REQUESTER_MASTER_TIME_ADDR + (0))

static int litepcie_read_time(struct litepcie_device *dev, struct timespec64 *ts)
{
	u32 nsec = 0, sec = 0;
	litepcie_writel(dev, CSR_TIME_CONTROLLER_CONTROL_ADDR,
			(TIME_CONTROL_ENABLE | TIME_CONTROL_LATCH));
	nsec = litepcie_readl(dev, CSR_TIME_CONTROLLER_TIME_NS_ADDR);
	sec = litepcie_readl(dev, CSR_TIME_CONTROLLER_TIME_S_ADDR);

	ts->tv_nsec = nsec;
	ts->tv_sec = sec;

	return 0;
}

static int litepcie_write_time(struct litepcie_device *dev, const struct timespec64 *ts)
{
	litepcie_writel(dev, CSR_TIME_CONTROLLER_OVERRIDE_TIME_NS_ADDR, ts->tv_nsec);
	litepcie_writel(dev, CSR_TIME_CONTROLLER_OVERRIDE_TIME_S_ADDR, ts->tv_sec);
	litepcie_writel(dev, CSR_TIME_CONTROLLER_CONTROL_ADDR,
			(TIME_CONTROL_ENABLE | TIME_CONTROL_OVERRIDE));

	return 0;
}

static int litepcie_ptp_gettimex64(struct ptp_clock_info *ptp,
                   struct timespec64 *ts,
                   struct ptp_system_timestamp *sts)
{
	struct litepcie_device *dev = container_of(ptp, struct litepcie_device,
							   ptp_caps);
	unsigned long flags;

	spin_lock_irqsave(&dev->tmreg_lock, flags);

	ptp_read_system_prets(sts);
	litepcie_read_time(dev, ts);
	ptp_read_system_postts(sts);

	spin_unlock_irqrestore(&dev->tmreg_lock, flags);

	return 0;
}

static int litepcie_ptp_settime(struct ptp_clock_info *ptp, const struct timespec64 *ts)
{
	struct litepcie_device *dev = container_of(ptp, struct litepcie_device,
							   ptp_caps);
	unsigned long flags;

	spin_lock_irqsave(&dev->tmreg_lock, flags);

	litepcie_write_time(dev, ts);

	spin_unlock_irqrestore(&dev->tmreg_lock, flags);

	return 0; // Return success
}

static int litepcie_ptp_adjfine(struct ptp_clock_info *ptp, long scaled_ppm)
{
#if 1
	if (scaled_ppm != 0)
		return -EOPNOTSUPP;
#else
	struct litepcie_device *dev = container_of(ptp, struct litepcie_device,
							   ptp_caps);
    int neg_adj = 0;
    u64 rate;
    u32 inca;

    if (scaled_ppm < 0) {
        neg_adj = 1;
        scaled_ppm = -scaled_ppm;
    }
    rate = scaled_ppm;
    rate <<= 14;
    rate = div_u64(rate, 78125);

    inca = rate & INCVALUE_MASK;
    if (neg_adj)
        inca |= ISGN;

    litepcie_write_time(IGC_TIMINCA, inca);
#endif

    return 0;
}

static int litepcie_ptp_adjtime(struct ptp_clock_info *ptp, s64 delta)
{
	struct litepcie_device *dev = container_of(ptp, struct litepcie_device,
							   ptp_caps);
	struct timespec64 now, then = ns_to_timespec64(delta);
	unsigned long flags;

	spin_lock_irqsave(&dev->tmreg_lock, flags);

	litepcie_read_time(dev, &now);
	now = timespec64_add(now, then);
	litepcie_write_time(dev, &now);

	spin_unlock_irqrestore(&dev->tmreg_lock, flags);
	return 0; // Return success
}

static int litepcie_phc_get_syncdevicetime(ktime_t *device,
                      struct system_counterval_t *system,
                      void *ctx)
{
	u32 t1_curr_h, t1_curr_l;
	u32 t2_curr_h, t2_curr_l;
	u32 reg;
	struct litepcie_device *dev = ctx;
	ktime_t t1, t2_curr;
	int count = 100;
	struct timespec64 ts;

	/* Get a snapshot of system clocks to use as historic value. */
	ktime_get_snapshot(&dev->snapshot);

	/* request */

	litepcie_writel(dev, CSR_PTM_REQUESTER_CONTROL_ADDR,
		PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER);
	/* wait until valid */
	do {
		reg = litepcie_readl(dev, CSR_PTM_REQUESTER_STATUS_ADDR);
		if ((reg & PTM_STATUS_VALID) != 0)
			break;
	}while (--count);

	if (!count) {
		printk("Exceeded number of tries for PTM cycle\n");
		return -ETIMEDOUT;
	}

#if 1
	t1_curr_l = litepcie_readl(dev, PTM_T1_TIME_L);
	t1_curr_h = litepcie_readl(dev, PTM_T1_TIME_H);
#if 1
	t1 = ktime_set(t1_curr_h, t1_curr_l);
#else
	t1_curr = ((u64)t1_curr_h << 32 | t1_curr_l);
	t1 = ns_to_ktime(t1_curr);
#endif
#else
	litepcie_read_time(dev, &ts);
	t1 = ktime_set(ts.tv_sec, ts.tv_nsec);
#endif

	t2_curr_l = litepcie_readl(dev, PTM_MASTER_TIME_L);
	t2_curr_h = litepcie_readl(dev, PTM_MASTER_TIME_H);
	t2_curr = ((u64)t2_curr_h << 32 | t2_curr_l);

	*device = t1;
#if IS_ENABLED(CONFIG_X86_TSC) && !defined(CONFIG_UML)
	*system = convert_art_ns_to_tsc(t2_curr);
#else
    *system (struct system_counterval_t) { };
#endif


	return 0;
}

static int litepcie_ptp_getcrosststamp(struct ptp_clock_info *ptp,
                  struct system_device_crosststamp *cts)
{
	struct litepcie_device *dev= container_of(ptp, struct litepcie_device,
                           ptp_caps);

	return get_device_system_crosststamp(litepcie_phc_get_syncdevicetime,
                         dev, &dev->snapshot, cts);
}

static int litepcie_ptp_enable(struct ptp_clock_info __always_unused *ptp,
                 struct ptp_clock_request __always_unused *request,
                 int __always_unused on)
{
    return -EOPNOTSUPP;
}

static struct ptp_clock_info litepcie_ptp_info = {
	.owner          = THIS_MODULE,
	.name           = LITEPCIE_NAME,
	.max_adj        = 1000000000,
	.n_alarm        = 0,
	.n_ext_ts       = 0,
	.n_per_out      = 0,
	.n_pins         = 0,
	.pps            = 0,
	.gettimex64     = litepcie_ptp_gettimex64,
	.settime64      = litepcie_ptp_settime,
	.adjtime        = litepcie_ptp_adjtime,
	.adjfine        = litepcie_ptp_adjfine,
	.getcrosststamp = litepcie_ptp_getcrosststamp,
	.enable         = litepcie_ptp_enable,
};

static int litepcie_pci_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	int ret = 0;
	int irqs = 0;
	uint8_t rev_id;
	int i;
	char fpga_identifier[256];
	struct litepcie_device *litepcie_dev = NULL;
#ifdef CSR_UART_XOVER_RXTX_ADDR
	struct resource *tty_res = NULL;
#endif

	dev_info(&dev->dev, "\e[1m[Probing device]\e[0m\n");

	litepcie_dev = devm_kzalloc(&dev->dev, sizeof(struct litepcie_device), GFP_KERNEL);
	if (!litepcie_dev) {
		ret = -ENOMEM;
		goto fail1;
	}

	pci_set_drvdata(dev, litepcie_dev);
	litepcie_dev->dev = dev;
	spin_lock_init(&litepcie_dev->lock);

	ret = pcim_enable_device(dev);
	if (ret != 0) {
		dev_err(&dev->dev, "Cannot enable device\n");
		goto fail1;
	}

	ret = -EIO;

	/* Check device version */
	pci_read_config_byte(dev, PCI_REVISION_ID, &rev_id);
	if (rev_id != 0) {
		dev_err(&dev->dev, "Unsupported device version %d\n", rev_id);
		goto fail1;
	}

	/* Check bar0 config */
	if (!(pci_resource_flags(dev, 0) & IORESOURCE_MEM)) {
		dev_err(&dev->dev, "Invalid BAR0 configuration\n");
		goto fail1;
	}

	if (pcim_iomap_regions(dev, BIT(0), LITEPCIE_NAME) < 0) {
		dev_err(&dev->dev, "Could not request regions\n");
		goto fail1;
	}

	litepcie_dev->bar0_addr = pcim_iomap_table(dev)[0];
	if (!litepcie_dev->bar0_addr) {
		dev_err(&dev->dev, "Could not map BAR0\n");
		goto fail1;
	}

	/* Reset LitePCIe core */
#ifdef CSR_CTRL_RESET_ADDR
	litepcie_writel(litepcie_dev, CSR_CTRL_RESET_ADDR, 1);
	msleep(10);
#endif

	/* Show identifier */
	for (i = 0; i < 256; i++)
		fpga_identifier[i] = litepcie_readl(litepcie_dev, CSR_IDENTIFIER_MEM_BASE + i*4);
	dev_info(&dev->dev, "Version %s\n", fpga_identifier);

	ret = pci_enable_ptm(dev, NULL);
	if (ret < 0)
		dev_info(&dev->dev, "PCIe PTM not supported by PCIe bus/controller\n");
	else
		dev_info(&dev->dev, "PCIe PTM supported by PCIe bus/controller\n");

	pci_set_master(dev);
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 18, 0)
	ret = pci_set_dma_mask(dev, DMA_BIT_MASK(DMA_ADDR_WIDTH));
#else
	ret = dma_set_mask(&dev->dev, DMA_BIT_MASK(DMA_ADDR_WIDTH));
#endif
	if (ret) {
		dev_err(&dev->dev, "Failed to set DMA mask\n");
		goto fail1;
	};


/* MSI-X */
#ifdef CSR_PCIE_MSI_PBA_ADDR
	irqs = pci_alloc_irq_vectors(dev, 1, 32, PCI_IRQ_MSIX);
/* MSI Single / MultiVector */
#else
	irqs = pci_alloc_irq_vectors(dev, 1, 32, PCI_IRQ_MSI);
#endif
	if (irqs < 0) {
		dev_err(&dev->dev, "Failed to enable MSI\n");
		ret = irqs;
		goto fail1;
	}
/* MSI-X */
#ifdef CSR_PCIE_MSI_PBA_ADDR
	dev_info(&dev->dev, "%d MSI-X IRQs allocated.\n", irqs);
/* MSI Single / MultiVector */
#else
	dev_info(&dev->dev, "%d MSI IRQs allocated.\n", irqs);
#endif

	litepcie_dev->irqs = 0;
	for (i = 0; i < irqs; i++) {
		int irq = pci_irq_vector(dev, i);

		ret = request_irq(irq, litepcie_interrupt, 0, LITEPCIE_NAME, litepcie_dev);
		if (ret < 0) {
			dev_err(&dev->dev, " Failed to allocate IRQ %d\n", dev->irq);
			while (--i >= 0) {
				irq = pci_irq_vector(dev, i);
				free_irq(irq, dev);
			}
			goto fail2;
		}
		litepcie_dev->irqs += 1;
	}

	litepcie_dev->channels = DMA_CHANNELS;

	/* create all chardev in /dev */
	ret = litepcie_alloc_chdev(litepcie_dev);
	if (ret) {
		dev_err(&dev->dev, "Failed to allocate character device\n");
		goto fail2;
	}

	for (i = 0; i < litepcie_dev->channels; i++) {
		litepcie_dev->chan[i].index = i;
		litepcie_dev->chan[i].block_size = DMA_BUFFER_SIZE;
		litepcie_dev->chan[i].minor = litepcie_dev->minor_base + i;
		litepcie_dev->chan[i].litepcie_dev = litepcie_dev;
		litepcie_dev->chan[i].dma.writer_lock = 0;
		litepcie_dev->chan[i].dma.reader_lock = 0;
		init_waitqueue_head(&litepcie_dev->chan[i].wait_rd);
		init_waitqueue_head(&litepcie_dev->chan[i].wait_wr);
		switch (i) {
#ifdef CSR_PCIE_DMA7_BASE
		case 7: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA7_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA7_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA7_READER_INTERRUPT;
	}
	break;
#endif
#ifdef CSR_PCIE_DMA6_BASE
		case 6: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA6_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA6_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA6_READER_INTERRUPT;
	}
	break;
#endif
#ifdef CSR_PCIE_DMA5_BASE
		case 5: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA5_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA5_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA5_READER_INTERRUPT;
	}
	break;
#endif
#ifdef CSR_PCIE_DMA4_BASE
		case 4: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA4_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA4_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA4_READER_INTERRUPT;
	}
	break;
#endif
#ifdef CSR_PCIE_DMA3_BASE
		case 3: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA3_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA3_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA3_READER_INTERRUPT;
	}
	break;
#endif
#ifdef CSR_PCIE_DMA2_BASE
		case 2: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA2_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA2_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA2_READER_INTERRUPT;
	}
	break;
#endif
#ifdef CSR_PCIE_DMA1_BASE
		case 1: {
		litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA1_BASE;
		litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA1_WRITER_INTERRUPT;
		litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA1_READER_INTERRUPT;
	}
	break;
#endif
		default:
			{
				litepcie_dev->chan[i].dma.base = CSR_PCIE_DMA0_BASE;
				litepcie_dev->chan[i].dma.writer_interrupt = PCIE_DMA0_WRITER_INTERRUPT;
				litepcie_dev->chan[i].dma.reader_interrupt = PCIE_DMA0_READER_INTERRUPT;
			}
			break;
		}
	}

	/* allocate all dma buffers */
	ret = litepcie_dma_init(litepcie_dev);
	if (ret) {
		dev_err(&dev->dev, "Failed to allocate DMA\n");
		goto fail3;
	}

#ifdef CSR_UART_XOVER_RXTX_ADDR
	tty_res = devm_kzalloc(&dev->dev, sizeof(struct resource), GFP_KERNEL);
	if (!tty_res)
		return -ENOMEM;
	tty_res->start =
		(resource_size_t) litepcie_dev->bar0_addr +
		CSR_UART_XOVER_RXTX_ADDR - CSR_BASE;
	tty_res->flags = IORESOURCE_REG;
	litepcie_dev->uart = platform_device_register_simple("liteuart", litepcie_minor_idx, tty_res, 1);
	if (IS_ERR(litepcie_dev->uart)) {
		ret = PTR_ERR(litepcie_dev->uart);
		goto fail3;
	}
#endif

	/* PTP */
	litepcie_dev->ptp_caps = litepcie_ptp_info;
	litepcie_dev->litepcie_ptp_clock = ptp_clock_register(&litepcie_dev->ptp_caps, &dev->dev);
	if (IS_ERR(litepcie_dev->litepcie_ptp_clock)) {
		return PTR_ERR(litepcie_dev->litepcie_ptp_clock);
	}

	/* enable timer (time) counter */
	litepcie_writel(litepcie_dev, CSR_TIME_CONTROLLER_CONTROL_ADDR, TIME_CONTROL_ENABLE);

	litepcie_writel(litepcie_dev, CSR_PTM_REQUESTER_CONTROL_ADDR, PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER);
	litepcie_writel(litepcie_dev, CSR_PTM_REQUESTER_CONTROL_ADDR, PTM_CONTROL_ENABLE | PTM_CONTROL_TRIGGER);

	spin_lock_init(&litepcie_dev->tmreg_lock);

	return 0;

fail3:
	litepcie_free_chdev(litepcie_dev);
fail2:
	pci_free_irq_vectors(dev);
fail1:
	return ret;
}

static void litepcie_pci_remove(struct pci_dev *dev)
{
	int i, irq;
	struct litepcie_device *litepcie_dev;

	litepcie_dev = pci_get_drvdata(dev);

	dev_info(&dev->dev, "\e[1m[Removing device]\e[0m\n");

	if (litepcie_dev->litepcie_ptp_clock) {
		ptp_clock_unregister(litepcie_dev->litepcie_ptp_clock);
		litepcie_dev->litepcie_ptp_clock = NULL;
	}

	/* Stop the DMAs */
	litepcie_stop_dma(litepcie_dev);

	/* Disable all interrupts */
	litepcie_writel(litepcie_dev, CSR_PCIE_MSI_ENABLE_ADDR, 0);

	/* Free all interrupts */
	for (i = 0; i < litepcie_dev->irqs; i++) {
		irq = pci_irq_vector(dev, i);
		free_irq(irq, litepcie_dev);
	}

	platform_device_unregister(litepcie_dev->uart);

	litepcie_free_chdev(litepcie_dev);

	pci_free_irq_vectors(dev);
}

static const struct pci_device_id litepcie_pci_ids[] = {
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_S7_GEN2_X1), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_S7_GEN2_X2), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_S7_GEN2_X4), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_S7_GEN2_X8), },

	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN2_X1), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN2_X2), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN2_X4), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN2_X8), },

	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN3_X1), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN3_X2), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN3_X4), },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_US_GEN3_X8), },

	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN2_X1),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN2_X2),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN2_X4),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN2_X8),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN2_X16), },

	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN3_X1),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN3_X2),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN3_X4),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN3_X8),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN3_X16), },

	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN4_X1),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN4_X2),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN4_X4),  },
	{ PCI_DEVICE(PCIE_FPGA_VENDOR_ID, PCIE_FPGA_DEVICE_ID_USP_GEN4_X8),  },

	{ 0, }
};
MODULE_DEVICE_TABLE(pci, litepcie_pci_ids);

static struct pci_driver litepcie_pci_driver = {
	.name = LITEPCIE_NAME,
	.id_table = litepcie_pci_ids,
	.probe = litepcie_pci_probe,
	.remove = litepcie_pci_remove,
};


static int __init litepcie_module_init(void)
{
	int ret;

	litepcie_class = class_create(THIS_MODULE, LITEPCIE_NAME);
	if (!litepcie_class) {
		ret = -EEXIST;
		pr_err(" Failed to create class\n");
		goto fail_create_class;
	}

	ret = alloc_chrdev_region(&litepcie_dev_t, 0, LITEPCIE_MINOR_COUNT, LITEPCIE_NAME);
	if (ret < 0) {
		pr_err(" Could not allocate char device\n");
		goto fail_alloc_chrdev_region;
	}
	litepcie_major = MAJOR(litepcie_dev_t);
	litepcie_minor_idx = MINOR(litepcie_dev_t);

	ret = pci_register_driver(&litepcie_pci_driver);
	if (ret < 0) {
		pr_err(" Error while registering PCI driver\n");
		goto fail_register;
	}

	return 0;

fail_register:
	unregister_chrdev_region(litepcie_dev_t, LITEPCIE_MINOR_COUNT);
fail_alloc_chrdev_region:
	class_destroy(litepcie_class);
fail_create_class:
	return ret;
}

static void __exit litepcie_module_exit(void)
{
	pci_unregister_driver(&litepcie_pci_driver);
	unregister_chrdev_region(litepcie_dev_t, LITEPCIE_MINOR_COUNT);
	class_destroy(litepcie_class);
}


module_init(litepcie_module_init);
module_exit(litepcie_module_exit);

MODULE_LICENSE("GPL");
