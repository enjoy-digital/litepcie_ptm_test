//--------------------------------------------------------------------------------
// Auto-generated by LiteX (ff67781f) on 2023-07-28 14:18:40
//--------------------------------------------------------------------------------
#ifndef __GENERATED_CSR_H
#define __GENERATED_CSR_H

#ifndef CSR_BASE
#define CSR_BASE 0x0L
#endif

/* ctrl */
#define CSR_CTRL_BASE (CSR_BASE + 0x0L)
#define CSR_CTRL_RESET_ADDR (CSR_BASE + 0x0L)
#define CSR_CTRL_RESET_SIZE 1
#define CSR_CTRL_RESET_SOC_RST_OFFSET 0
#define CSR_CTRL_RESET_SOC_RST_SIZE 1
#define CSR_CTRL_RESET_CPU_RST_OFFSET 1
#define CSR_CTRL_RESET_CPU_RST_SIZE 1
#define CSR_CTRL_SCRATCH_ADDR (CSR_BASE + 0x4L)
#define CSR_CTRL_SCRATCH_SIZE 1
#define CSR_CTRL_BUS_ERRORS_ADDR (CSR_BASE + 0x8L)
#define CSR_CTRL_BUS_ERRORS_SIZE 1

/* dna */
#define CSR_DNA_BASE (CSR_BASE + 0x800L)
#define CSR_DNA_ID_ADDR (CSR_BASE + 0x800L)
#define CSR_DNA_ID_SIZE 2

/* identifier_mem */
#define CSR_IDENTIFIER_MEM_BASE (CSR_BASE + 0x1000L)

/* pcie_msi */
#define CSR_PCIE_MSI_BASE (CSR_BASE + 0x1800L)
#define CSR_PCIE_MSI_ENABLE_ADDR (CSR_BASE + 0x1800L)
#define CSR_PCIE_MSI_ENABLE_SIZE 1
#define CSR_PCIE_MSI_RESERVED0_ADDR (CSR_BASE + 0x1804L)
#define CSR_PCIE_MSI_RESERVED0_SIZE 1
#define CSR_PCIE_MSI_PBA_ADDR (CSR_BASE + 0x1808L)
#define CSR_PCIE_MSI_PBA_SIZE 1
#define CSR_PCIE_MSI_RESERVED1_ADDR (CSR_BASE + 0x180cL)
#define CSR_PCIE_MSI_RESERVED1_SIZE 1

/* pcie_msi_table */
#define CSR_PCIE_MSI_TABLE_BASE (CSR_BASE + 0x2000L)

/* leds */
#define CSR_LEDS_BASE (CSR_BASE + 0x2800L)
#define CSR_LEDS_OUT_ADDR (CSR_BASE + 0x2800L)
#define CSR_LEDS_OUT_SIZE 1

/* pcie_dma0 */
#define CSR_PCIE_DMA0_BASE (CSR_BASE + 0x3000L)
#define CSR_PCIE_DMA0_WRITER_ENABLE_ADDR (CSR_BASE + 0x3000L)
#define CSR_PCIE_DMA0_WRITER_ENABLE_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_ADDR (CSR_BASE + 0x3004L)
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_SIZE 2
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_ADDRESS_LSB_OFFSET 0
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_ADDRESS_LSB_SIZE 32
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_LENGTH_OFFSET 32
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_LENGTH_SIZE 24
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_IRQ_DISABLE_OFFSET 56
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_IRQ_DISABLE_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_LAST_DISABLE_OFFSET 57
#define CSR_PCIE_DMA0_WRITER_TABLE_VALUE_LAST_DISABLE_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_WE_ADDR (CSR_BASE + 0x300cL)
#define CSR_PCIE_DMA0_WRITER_TABLE_WE_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_WE_ADDRESS_MSB_OFFSET 0
#define CSR_PCIE_DMA0_WRITER_TABLE_WE_ADDRESS_MSB_SIZE 32
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_PROG_N_ADDR (CSR_BASE + 0x3010L)
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_PROG_N_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_STATUS_ADDR (CSR_BASE + 0x3014L)
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_STATUS_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_STATUS_INDEX_OFFSET 0
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_STATUS_INDEX_SIZE 16
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_STATUS_COUNT_OFFSET 16
#define CSR_PCIE_DMA0_WRITER_TABLE_LOOP_STATUS_COUNT_SIZE 16
#define CSR_PCIE_DMA0_WRITER_TABLE_LEVEL_ADDR (CSR_BASE + 0x3018L)
#define CSR_PCIE_DMA0_WRITER_TABLE_LEVEL_SIZE 1
#define CSR_PCIE_DMA0_WRITER_TABLE_RESET_ADDR (CSR_BASE + 0x301cL)
#define CSR_PCIE_DMA0_WRITER_TABLE_RESET_SIZE 1
#define CSR_PCIE_DMA0_READER_ENABLE_ADDR (CSR_BASE + 0x3020L)
#define CSR_PCIE_DMA0_READER_ENABLE_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_ADDR (CSR_BASE + 0x3024L)
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_SIZE 2
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_ADDRESS_LSB_OFFSET 0
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_ADDRESS_LSB_SIZE 32
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_LENGTH_OFFSET 32
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_LENGTH_SIZE 24
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_IRQ_DISABLE_OFFSET 56
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_IRQ_DISABLE_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_LAST_DISABLE_OFFSET 57
#define CSR_PCIE_DMA0_READER_TABLE_VALUE_LAST_DISABLE_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_WE_ADDR (CSR_BASE + 0x302cL)
#define CSR_PCIE_DMA0_READER_TABLE_WE_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_WE_ADDRESS_MSB_OFFSET 0
#define CSR_PCIE_DMA0_READER_TABLE_WE_ADDRESS_MSB_SIZE 32
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_PROG_N_ADDR (CSR_BASE + 0x3030L)
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_PROG_N_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_STATUS_ADDR (CSR_BASE + 0x3034L)
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_STATUS_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_STATUS_INDEX_OFFSET 0
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_STATUS_INDEX_SIZE 16
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_STATUS_COUNT_OFFSET 16
#define CSR_PCIE_DMA0_READER_TABLE_LOOP_STATUS_COUNT_SIZE 16
#define CSR_PCIE_DMA0_READER_TABLE_LEVEL_ADDR (CSR_BASE + 0x3038L)
#define CSR_PCIE_DMA0_READER_TABLE_LEVEL_SIZE 1
#define CSR_PCIE_DMA0_READER_TABLE_RESET_ADDR (CSR_BASE + 0x303cL)
#define CSR_PCIE_DMA0_READER_TABLE_RESET_SIZE 1
#define CSR_PCIE_DMA0_LOOPBACK_ENABLE_ADDR (CSR_BASE + 0x3040L)
#define CSR_PCIE_DMA0_LOOPBACK_ENABLE_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_ADDR (CSR_BASE + 0x3044L)
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_DEPTH_OFFSET 0
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_DEPTH_SIZE 24
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_SCRATCH_OFFSET 24
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_SCRATCH_SIZE 4
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_LEVEL_MODE_OFFSET 31
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_CONTROL_LEVEL_MODE_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_STATUS_ADDR (CSR_BASE + 0x3048L)
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_STATUS_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_STATUS_LEVEL_OFFSET 0
#define CSR_PCIE_DMA0_BUFFERING_READER_FIFO_STATUS_LEVEL_SIZE 24
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_ADDR (CSR_BASE + 0x304cL)
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_DEPTH_OFFSET 0
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_DEPTH_SIZE 24
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_SCRATCH_OFFSET 24
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_SCRATCH_SIZE 4
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_LEVEL_MODE_OFFSET 31
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_CONTROL_LEVEL_MODE_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_STATUS_ADDR (CSR_BASE + 0x3050L)
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_STATUS_SIZE 1
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_STATUS_LEVEL_OFFSET 0
#define CSR_PCIE_DMA0_BUFFERING_WRITER_FIFO_STATUS_LEVEL_SIZE 24

/* pcie_endpoint */
#define CSR_PCIE_ENDPOINT_BASE (CSR_BASE + 0x3800L)
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_ADDR (CSR_BASE + 0x3800L)
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_STATUS_OFFSET 0
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_STATUS_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_RATE_OFFSET 1
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_RATE_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_WIDTH_OFFSET 2
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_WIDTH_SIZE 2
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_LTSSM_OFFSET 4
#define CSR_PCIE_ENDPOINT_PHY_LINK_STATUS_LTSSM_SIZE 6
#define CSR_PCIE_ENDPOINT_PHY_MSI_ENABLE_ADDR (CSR_BASE + 0x3804L)
#define CSR_PCIE_ENDPOINT_PHY_MSI_ENABLE_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_MSIX_ENABLE_ADDR (CSR_BASE + 0x3808L)
#define CSR_PCIE_ENDPOINT_PHY_MSIX_ENABLE_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_BUS_MASTER_ENABLE_ADDR (CSR_BASE + 0x380cL)
#define CSR_PCIE_ENDPOINT_PHY_BUS_MASTER_ENABLE_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_MAX_REQUEST_SIZE_ADDR (CSR_BASE + 0x3810L)
#define CSR_PCIE_ENDPOINT_PHY_MAX_REQUEST_SIZE_SIZE 1
#define CSR_PCIE_ENDPOINT_PHY_MAX_PAYLOAD_SIZE_ADDR (CSR_BASE + 0x3814L)
#define CSR_PCIE_ENDPOINT_PHY_MAX_PAYLOAD_SIZE_SIZE 1

/* pcie_phy */
#define CSR_PCIE_PHY_BASE (CSR_BASE + 0x4000L)
#define CSR_PCIE_PHY_PHY_LINK_STATUS_ADDR (CSR_BASE + 0x4000L)
#define CSR_PCIE_PHY_PHY_LINK_STATUS_SIZE 1
#define CSR_PCIE_PHY_PHY_LINK_STATUS_STATUS_OFFSET 0
#define CSR_PCIE_PHY_PHY_LINK_STATUS_STATUS_SIZE 1
#define CSR_PCIE_PHY_PHY_LINK_STATUS_RATE_OFFSET 1
#define CSR_PCIE_PHY_PHY_LINK_STATUS_RATE_SIZE 1
#define CSR_PCIE_PHY_PHY_LINK_STATUS_WIDTH_OFFSET 2
#define CSR_PCIE_PHY_PHY_LINK_STATUS_WIDTH_SIZE 2
#define CSR_PCIE_PHY_PHY_LINK_STATUS_LTSSM_OFFSET 4
#define CSR_PCIE_PHY_PHY_LINK_STATUS_LTSSM_SIZE 6
#define CSR_PCIE_PHY_PHY_MSI_ENABLE_ADDR (CSR_BASE + 0x4004L)
#define CSR_PCIE_PHY_PHY_MSI_ENABLE_SIZE 1
#define CSR_PCIE_PHY_PHY_MSIX_ENABLE_ADDR (CSR_BASE + 0x4008L)
#define CSR_PCIE_PHY_PHY_MSIX_ENABLE_SIZE 1
#define CSR_PCIE_PHY_PHY_BUS_MASTER_ENABLE_ADDR (CSR_BASE + 0x400cL)
#define CSR_PCIE_PHY_PHY_BUS_MASTER_ENABLE_SIZE 1
#define CSR_PCIE_PHY_PHY_MAX_REQUEST_SIZE_ADDR (CSR_BASE + 0x4010L)
#define CSR_PCIE_PHY_PHY_MAX_REQUEST_SIZE_SIZE 1
#define CSR_PCIE_PHY_PHY_MAX_PAYLOAD_SIZE_ADDR (CSR_BASE + 0x4014L)
#define CSR_PCIE_PHY_PHY_MAX_PAYLOAD_SIZE_SIZE 1

/* ptm_requester */
#define CSR_PTM_REQUESTER_BASE (CSR_BASE + 0x4800L)
#define CSR_PTM_REQUESTER_CONTROL_ADDR (CSR_BASE + 0x4800L)
#define CSR_PTM_REQUESTER_CONTROL_SIZE 1
#define CSR_PTM_REQUESTER_CONTROL_ENABLE_OFFSET 0
#define CSR_PTM_REQUESTER_CONTROL_ENABLE_SIZE 1
#define CSR_PTM_REQUESTER_CONTROL_TRIGGER_OFFSET 1
#define CSR_PTM_REQUESTER_CONTROL_TRIGGER_SIZE 1
#define CSR_PTM_REQUESTER_STATUS_ADDR (CSR_BASE + 0x4804L)
#define CSR_PTM_REQUESTER_STATUS_SIZE 1
#define CSR_PTM_REQUESTER_STATUS_VALID_OFFSET 0
#define CSR_PTM_REQUESTER_STATUS_VALID_SIZE 1
#define CSR_PTM_REQUESTER_PHY_TX_DELAY_ADDR (CSR_BASE + 0x4808L)
#define CSR_PTM_REQUESTER_PHY_TX_DELAY_SIZE 1
#define CSR_PTM_REQUESTER_PHY_RX_DELAY_ADDR (CSR_BASE + 0x480cL)
#define CSR_PTM_REQUESTER_PHY_RX_DELAY_SIZE 1
#define CSR_PTM_REQUESTER_MASTER_TIME_ADDR (CSR_BASE + 0x4810L)
#define CSR_PTM_REQUESTER_MASTER_TIME_SIZE 2
#define CSR_PTM_REQUESTER_LINK_DELAY_ADDR (CSR_BASE + 0x4818L)
#define CSR_PTM_REQUESTER_LINK_DELAY_SIZE 1
#define CSR_PTM_REQUESTER_T1_TIME_ADDR (CSR_BASE + 0x481cL)
#define CSR_PTM_REQUESTER_T1_TIME_SIZE 2
#define CSR_PTM_REQUESTER_T4_TIME_ADDR (CSR_BASE + 0x4824L)
#define CSR_PTM_REQUESTER_T4_TIME_SIZE 2

/* time_controller */
#define CSR_TIME_CONTROLLER_BASE (CSR_BASE + 0x5000L)
#define CSR_TIME_CONTROLLER_CONTROL_ADDR (CSR_BASE + 0x5000L)
#define CSR_TIME_CONTROLLER_CONTROL_SIZE 1
#define CSR_TIME_CONTROLLER_CONTROL_ENABLE_OFFSET 0
#define CSR_TIME_CONTROLLER_CONTROL_ENABLE_SIZE 1
#define CSR_TIME_CONTROLLER_CONTROL_LATCH_OFFSET 1
#define CSR_TIME_CONTROLLER_CONTROL_LATCH_SIZE 1
#define CSR_TIME_CONTROLLER_CONTROL_OVERRIDE_OFFSET 2
#define CSR_TIME_CONTROLLER_CONTROL_OVERRIDE_SIZE 1
#define CSR_TIME_CONTROLLER_TIME_NS_ADDR (CSR_BASE + 0x5004L)
#define CSR_TIME_CONTROLLER_TIME_NS_SIZE 1
#define CSR_TIME_CONTROLLER_TIME_S_ADDR (CSR_BASE + 0x5008L)
#define CSR_TIME_CONTROLLER_TIME_S_SIZE 1
#define CSR_TIME_CONTROLLER_OVERRIDE_TIME_NS_ADDR (CSR_BASE + 0x500cL)
#define CSR_TIME_CONTROLLER_OVERRIDE_TIME_NS_SIZE 1
#define CSR_TIME_CONTROLLER_OVERRIDE_TIME_S_ADDR (CSR_BASE + 0x5010L)
#define CSR_TIME_CONTROLLER_OVERRIDE_TIME_S_SIZE 1

/* xadc */
#define CSR_XADC_BASE (CSR_BASE + 0x5800L)
#define CSR_XADC_TEMPERATURE_ADDR (CSR_BASE + 0x5800L)
#define CSR_XADC_TEMPERATURE_SIZE 1
#define CSR_XADC_VCCINT_ADDR (CSR_BASE + 0x5804L)
#define CSR_XADC_VCCINT_SIZE 1
#define CSR_XADC_VCCAUX_ADDR (CSR_BASE + 0x5808L)
#define CSR_XADC_VCCAUX_SIZE 1
#define CSR_XADC_VCCBRAM_ADDR (CSR_BASE + 0x580cL)
#define CSR_XADC_VCCBRAM_SIZE 1
#define CSR_XADC_EOC_ADDR (CSR_BASE + 0x5810L)
#define CSR_XADC_EOC_SIZE 1
#define CSR_XADC_EOS_ADDR (CSR_BASE + 0x5814L)
#define CSR_XADC_EOS_SIZE 1

#endif
