// uniaxial stm32 code
/* USER CODE BEGIN Header */
/**
 ******************************************************************************
 * @file           : main.c
 * @brief          : Main program body
 ******************************************************************************
 * @attention
 *
 * Copyright (c) 2025 STMicroelectronics.
 * All rights reserved.
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 ******************************************************************************
 */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h> //atoi
#include <string.h>

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define ADS1115_I2C_ADDR (0x48 << 1)
#define FREEZE_THRESHOLD 50
#define MAX_CMD_LEN 32
#define MODBUS_POLY 0xA001
#define ADC_SETTLE_MS 10

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_I2C1_Init(void);
static void MX_USART1_UART_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
char uart2_rx_buf[MAX_CMD_LEN];
uint8_t uart2_byte = 0;
uint8_t rx_index = 0;

int16_t current_velocity = 1000;
int16_t current_acc = 50;
int16_t current_dec = 50;

int16_t adc_value;
float voltage;

int16_t last_adc_value = 0;
uint8_t freeze_counter = 0;

int16_t displacement_adc_value;
float displacement_voltage;

volatile bool command_ready = false;
char cmd_process_buf[MAX_CMD_LEN];

typedef enum {
  LOOP_START,
  LOOP_LOAD_SETTLE,
  LOOP_DISP_SETTLE,
  LOOP_TRANSMIT
} LoopState;

static LoopState loop_state = LOOP_START;
static uint32_t state_tick = 0;

void append_crc(uint8_t *frame, uint16_t len);
void modbus_send(uint8_t *frame, uint16_t len);

/* Helper Functions ----------------------------------------------------------*/
void UART2_Printf(const char *format, ...) {
  char buffer[128];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  HAL_UART_Transmit(&huart2, (uint8_t *)buffer, strlen(buffer), HAL_MAX_DELAY);
}

void ResetADC() {
  HAL_I2C_DeInit(&hi2c1);
  HAL_Delay(5); // Brief delay for I2C re-init (rare, freeze recovery only)
  HAL_I2C_Init(&hi2c1);
}

float ADS1115_ConvertToVoltage(int16_t adc_value) {
  return (((adc_value * 6.144 * 5.028) / (5.267 * 32767.0)));
}

HAL_StatusTypeDef ADS1115_Config(uint8_t channel) {
  uint8_t config[3];
  config[0] = 0x01;
  uint8_t mux = (channel <= 3) ? (0b100 + channel) : 0b100;
  config[1] = (1 << 7) | (mux << 4) | (0b000 << 1) | (1 << 0);
  config[2] = 0b10000011;
  return HAL_I2C_Master_Transmit(&hi2c1, ADS1115_I2C_ADDR, config, 3, 100);
}

int16_t ADS1115_ReadADC() {
  uint8_t data[2];
  uint8_t reg_pointer = 0x00;
  uint32_t timeout_counter = 0;
  const uint32_t MAX_TIMEOUT = 1000000;
  uint8_t config_reg_ptr = 0x01;
  uint8_t config_read_buffer[2];

  do {
    if (HAL_I2C_Master_Transmit(&hi2c1, ADS1115_I2C_ADDR, &config_reg_ptr, 1,
                                100) != HAL_OK)
      return 0;
    if (HAL_I2C_Master_Receive(&hi2c1, ADS1115_I2C_ADDR, config_read_buffer, 2,
                               100) != HAL_OK)
      return 0;
    timeout_counter++;
    if (timeout_counter > MAX_TIMEOUT)
      return 0;
  } while ((config_read_buffer[0] & 0x80) == 0);

  if (HAL_I2C_Master_Transmit(&hi2c1, ADS1115_I2C_ADDR, &reg_pointer, 1, 100) !=
      HAL_OK)
    return 0;
  if (HAL_I2C_Master_Receive(&hi2c1, ADS1115_I2C_ADDR, data, 2, 100) != HAL_OK)
    return 0;

  return (int16_t)((data[0] << 8) | data[1]);
}

void DetectAndRecoverFrozenADC() {
  int16_t current_value = ADS1115_ReadADC();
  if (current_value == 0 && last_adc_value == 0 && freeze_counter > 0) {
    ResetADC();
    freeze_counter = 0;
    return;
  }
  freeze_counter = (current_value == last_adc_value) ? freeze_counter + 1 : 0;
  last_adc_value = current_value;
  if (freeze_counter >= FREEZE_THRESHOLD) {
    ResetADC();
    freeze_counter = 0;
  }
}

void process_command(char *cmd) {
  if (strncmp(cmd, "VEL:", 4) == 0) {
    int v = atoi(cmd + 4);
    if (v >= -3000 && v <= 3000)
      current_velocity = v;
  } else if (strncmp(cmd, "ACC:", 4) == 0) {
    int a = atoi(cmd + 4);
    if (a >= 0 && a <= 3000)
      current_acc = a;
  } else if (strncmp(cmd, "DEC:", 4) == 0) {
    int d = atoi(cmd + 4);
    if (d >= 0 && d <= 3000)
      current_dec = d;
  } else if (strcmp(cmd, "START") == 0) {
    uint8_t frame[8];
    uint8_t en[] = {0x01, 0x06, 0x04, 0x05, 0x00, 0x83};
    uint8_t mode[] = {0x01, 0x06, 0x62, 0x00, 0x00, 0x02};
    uint8_t vel[] = {0x01,
                     0x06,
                     0x62,
                     0x03,
                     ((uint16_t)current_velocity >> 8),
                     (uint16_t)current_velocity & 0xFF};
    uint8_t acc[] = {
        0x01, 0x06, 0x62, 0x04, (current_acc >> 8), current_acc & 0xFF};
    uint8_t dec[] = {
        0x01, 0x06, 0x62, 0x05, (current_dec >> 8), current_dec & 0xFF};
    uint8_t start[] = {0x01, 0x06, 0x60, 0x02, 0x00, 0x10};

    memcpy(frame, en, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
    memcpy(frame, mode, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
    memcpy(frame, vel, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
    memcpy(frame, acc, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
    memcpy(frame, dec, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
    memcpy(frame, start, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);

  } else if (strcmp(cmd, "STOP") == 0) {
    uint8_t frame[8];
    uint8_t stop[] = {0x01, 0x06, 0x60, 0x02, 0x00, 0x40};
    uint8_t dis[] = {0x01, 0x06, 0x04, 0x05, 0x00, 0x03};
    memcpy(frame, stop, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
    memcpy(frame, dis, 6);
    append_crc(frame, 6);
    modbus_send(frame, 8);
  }

  // Relay controls
  else if (strcmp(cmd, "COMP") == 0) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_RESET);
  } else if (strcmp(cmd, "TENS") == 0) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
  } else if (strcmp(cmd, "STOP_RELAY") == 0) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
  }
}
uint16_t modbus_crc(uint8_t *data, uint16_t length) {
  uint16_t crc = 0xFFFF;
  for (uint16_t i = 0; i < length; i++) {
    crc ^= data[i];
    for (uint8_t j = 0; j < 8; j++) {
      if (crc & 0x01)
        crc = (crc >> 1) ^ MODBUS_POLY;
      else
        crc >>= 1;
    }
  }
  return crc;
}

void print_modbus_frame(uint8_t *frame, uint16_t len) {
  char msg[100];
  int pos = 0;
  pos += snprintf(msg + pos, sizeof(msg) - pos, "Sent: ");
  for (uint16_t i = 0; i < len; i++) {
    pos += snprintf(msg + pos, sizeof(msg) - pos, "%02X ", frame[i]);
  }
  pos += snprintf(msg + pos, sizeof(msg) - pos, "\r\n");
  HAL_UART_Transmit(&huart2, (uint8_t *)msg, pos, HAL_MAX_DELAY);
}

void append_crc(uint8_t *frame, uint16_t len) {
  uint16_t crc = modbus_crc(frame, len);
  frame[len] = crc & 0xFF;
  frame[len + 1] = (crc >> 8);
}

void modbus_send(uint8_t *frame, uint16_t len) {
  HAL_UART_Transmit(&huart1, frame, len, HAL_MAX_DELAY);
  print_modbus_frame(frame, len);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
  if (huart->Instance == USART2) {
    if (uart2_byte == '\n' || uart2_byte == '\r') {
      uart2_rx_buf[rx_index] = '\0';
      memcpy(cmd_process_buf, uart2_rx_buf, rx_index + 1);
      command_ready = true;
      rx_index = 0;
    } else if (rx_index < MAX_CMD_LEN - 1) {
      uart2_rx_buf[rx_index++] = uart2_byte;
    }
    HAL_UART_Receive_IT(&huart2, &uart2_byte, 1);
  }
}

/* USER CODE END 0 */

/**
 * @brief  The application entry point.
 * @retval int
 */
int main(void) {

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick.
   */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART2_UART_Init();
  MX_I2C1_Init();
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */
  HAL_UART_Receive_IT(&huart2, &uart2_byte, 1); // Start UART RX interrupt
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7, GPIO_PIN_SET);

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1) {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    if (command_ready) {
      process_command(cmd_process_buf);
      command_ready = false;
    }

    uint32_t now = HAL_GetTick();

    switch (loop_state) {
    case LOOP_START:
      DetectAndRecoverFrozenADC();
      if (ADS1115_Config(0) == HAL_OK) {
        state_tick = now;
        loop_state = LOOP_LOAD_SETTLE;
      }
      break;

    case LOOP_LOAD_SETTLE:
      if (now - state_tick >= ADC_SETTLE_MS) {
        adc_value = ADS1115_ReadADC();
        voltage = ADS1115_ConvertToVoltage(adc_value);
        if (ADS1115_Config(1) == HAL_OK) {
          state_tick = now;
          loop_state = LOOP_DISP_SETTLE;
        } else {
          loop_state = LOOP_START;
        }
      }
      break;

    case LOOP_DISP_SETTLE:
      if (now - state_tick >= ADC_SETTLE_MS) {
        displacement_adc_value = ADS1115_ReadADC();
        displacement_voltage = ADS1115_ConvertToVoltage(displacement_adc_value);
        loop_state = LOOP_TRANSMIT;
      }
      break;

    case LOOP_TRANSMIT: {
      char msg[64];
      snprintf(msg, sizeof(msg), "LOAD: %.3f kN, DISP: %.3f mm\r\n",
               1.9835 * voltage, (50 - displacement_voltage * 10));
      HAL_UART_Transmit(&huart2, (uint8_t *)msg, strlen(msg), HAL_MAX_DELAY);
      loop_state = LOOP_START;
      break;
    }
    }
  }
  /* USER CODE END 3 */
}

/**
 * @brief System Clock Configuration
 * @retval None
 */
void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
   */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE3);

  /** Initializes the RCC Oscillators according to the specified parameters
   * in the RCC_OscInitTypeDef structure.
   */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
   */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {
    Error_Handler();
  }
}

/**
 * @brief I2C1 Initialization Function
 * @param None
 * @retval None
 */
static void MX_I2C1_Init(void) {

  /* USER CODE BEGIN I2C1_Init 0 */

  /* USER CODE END I2C1_Init 0 */

  /* USER CODE BEGIN I2C1_Init 1 */

  /* USER CODE END I2C1_Init 1 */
  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK) {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C1_Init 2 */

  /* USER CODE END I2C1_Init 2 */
}

/**
 * @brief USART1 Initialization Function
 * @param None
 * @retval None
 */
static void MX_USART1_UART_Init(void) {

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK) {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */
}

/**
 * @brief USART2 Initialization Function
 * @param None
 * @retval None
 */
static void MX_USART2_UART_Init(void) {

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK) {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */
}

/**
 * @brief GPIO Initialization Function
 * @param None
 * @retval None
 */
static void MX_GPIO_Init(void) {
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, LD2_Pin | GPIO_PIN_7 | GPIO_PIN_8, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : LD2_Pin PA7 PA8 */
  GPIO_InitStruct.Pin = LD2_Pin | GPIO_PIN_7 | GPIO_PIN_8;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
 * @brief  This function is executed in case of error occurrence.
 * @retval None
 */
void Error_Handler(void) {
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1) {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
 * @brief  Reports the name of the source file and the source line number
 *         where the assert_param error has occurred.
 * @param  file: pointer to the source file name
 * @param  line: assert_param error line source number
 * @retval None
 */
void assert_failed(uint8_t *file, uint32_t line) {
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line
     number, ex: printf("Wrong parameters value: file %s on line %d\r\n", file,
     line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
