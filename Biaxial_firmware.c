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
#include <stdio.h>
#include <string.h>
#include <stdlib.h> // For atoi
#include <stdbool.h>
#include <stdarg.h>
#include <math.h>   // For isnan, isinf
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define CMD_READ_LOAD   0x01
#define I2C_TIMEOUT_MS  200
#define MA_WINDOW_SIZE 10
#define MAX_CMD_LEN 32
#define CMD_QUEUE_SIZE 8  // Circular buffer size for command queue
#define MODBUS_POLY 0xA001
#define PRELOAD_SPEED_RPM 40
#define PRELOAD_TOLERANCE 2.0f // +/- 1N tolerance to stop jitter
#define OVERLOAD_KN_THRESHOLD 10.0f


typedef enum {
    STATE_IDLE,
    STATE_PRELOAD_X,
    STATE_PRELOAD_Y,
    STATE_PRELOAD_ALL
} SystemState_t;

#define ENABLE_DEBUG_LOGS    0        /* 0 = disable heavy prints in sensor loop, 1 = enable for debug */
#define SCAN_PERIOD_MS       20U     // Load-cell scan period

volatile uint32_t last_scan_tick_ms = 0; /* used by scan scheduler */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;
I2C_HandleTypeDef hi2c2;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
char uart2_rx_buf[MAX_CMD_LEN];
uint8_t uart2_byte = 0;
uint8_t rx_index = 0;

// Sensor-related variables
const uint8_t lc_slave_addresses[4] = {0x14, 0x15, 0x16, 0x17};
const int num_sensors = 4;

SystemState_t current_state = STATE_IDLE;
float target_preload_force = 0.0f;
int16_t current_preload_vel = 0;
bool motor_target_reached[4] = {false, false, false, false};

volatile bool uart_cmd_ready = false;
char uart_cmd_pending[MAX_CMD_LEN];

// --- Command Queue (Circular Buffer) ---
char cmd_queue[CMD_QUEUE_SIZE][MAX_CMD_LEN];
volatile uint8_t cmd_queue_head = 0;  // Write index (ISR)
volatile uint8_t cmd_queue_tail = 0;  // Read index (main loop)
volatile uint8_t cmd_queue_count = 0; // Number of commands in queue

// --- Modbus TX Queue (Non-Blocking) ---
#define MB_QUEUE_SIZE 32
typedef enum { MB_IDLE, MB_TX_IN_PROGRESS, MB_WAITING_GAP } ModbusState;
volatile ModbusState mb_state = MB_IDLE;
uint8_t mb_tx_queue[MB_QUEUE_SIZE][8];  // All frames are 8 bytes
volatile uint8_t mb_head = 0;
volatile uint8_t mb_tail = 0;
volatile uint8_t mb_count = 0;
volatile uint32_t mb_gap_start = 0;
#define MB_INTER_FRAME_GAP_MS 5  // Gap between Modbus frames
volatile bool kill_switch_triggered=false;


// --- I2C Sensor Scan State Machine (Non-Blocking) ---
typedef enum { I2C_IDLE, I2C_WAIT_READY, I2C_TX_CMD, I2C_WAIT_DELAY, I2C_RX_DATA } I2C_ScanState;
volatile I2C_ScanState i2c_state = I2C_IDLE;
volatile uint8_t i2c_current_sensor = 0;
volatile uint32_t i2c_delay_start = 0;
uint8_t i2c_raw_data[4];
float sensor_loads[4] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile bool sensor_scan_complete = false;
#define I2C_RESPONSE_DELAY_MS 20  // Delay for sensor to prepare data
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_I2C2_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_I2C1_Init(void);
/* USER CODE BEGIN PFP */
void append_crc(uint8_t *frame, uint16_t len);
void modbus_send(uint8_t *frame, uint16_t len);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
// --- New global variables for 4-motor control ---
// Array to hold the velocity for each motor. M1, M2, M3, M4.
int16_t motor_velocities[4] = {100, 100, 100, 100};
// Constant acceleration and deceleration
const int16_t MOTOR_ACC_DEC = 100;
// Array of slave addresses for easy iteration
const uint8_t slave_addresses[4] = {0x01, 0x02, 0x03, 0x04};


// --- Forward declarations for our new helper functions ---
void start_motor(uint8_t slave_address, int16_t velocity);
void stop_motor(uint8_t slave_address);
void process_command(char* cmd);

static HAL_StatusTypeDef i2c_read_4bytes(uint8_t addr, uint8_t cmd, uint8_t out[4]);
static float float_from_le_bytes(const uint8_t b[4]);
HAL_StatusTypeDef get_load_as_float(uint8_t addr, float *out);
static void print_float_manual(float f, int precision);
void UART2_Printf(const char *format, ...);

// --- Non-Blocking Modbus Functions ---
void Modbus_Enqueue(uint8_t *frame, uint16_t len);
void Modbus_Process(void);

// --- Non-Blocking I2C Functions ---
void I2C_Scan_Start(void);
void I2C_Scan_Process(void);

/**
  * @brief  Starts a specific motor with its configured velocity.
  * @param  slave_address: The Modbus slave address of the motor to start.
  * @param  velocity: The velocity to set for the motor.
  * @retval None
  */
const char* i2c_error_str(uint32_t err) {
    if (err == HAL_I2C_ERROR_NONE) return "NONE";
    if (err & HAL_I2C_ERROR_BERR) return "BUS ERROR (BERR)";
    if (err & HAL_I2C_ERROR_ARLO) return "ARBITRATION LOST (ARLO)";
    if (err & HAL_I2C_ERROR_AF)   return "ACK FAILURE (AF/NACK)";
    if (err & HAL_I2C_ERROR_OVR)  return "OVERRUN (OVR)";
    if (err & HAL_I2C_ERROR_TIMEOUT) return "TIMEOUT";
    if (err & HAL_I2C_ERROR_SIZE) return "SIZE ERROR";
    return "UNKNOWN";
}
/*

HAL_StatusTypeDef i2c_read_4bytes(uint8_t addr, uint8_t cmd, uint8_t out[4]) {
    HAL_StatusTypeDef st;
    uint8_t devAddr = addr << 1;

    st = HAL_I2C_Master_Transmit(&hi2c2, devAddr, &cmd, 1, 50);
    if (st != HAL_OK) {
        uint32_t err = HAL_I2C_GetError(&hi2c2);
        UART2_Printf("TX failed st=%d, i2c_err=%s (0x%08lX)\r\n", st, i2c_error_str(err), err);
        return st;
    }

    HAL_Delay(10); // device processing time (tune)

    st = HAL_I2C_Master_Receive(&hi2c2, devAddr, out, 4, 100);
    if (st != HAL_OK) {
        uint32_t err = HAL_I2C_GetError(&hi2c2);
        UART2_Printf("RX failed st=%d, i2c_err=%s (0x%08lX)\r\n", st, i2c_error_str(err), err);

        // If it's an ACK failure or timeout, try a short backoff and retry
        if (err & (HAL_I2C_ERROR_AF | HAL_I2C_ERROR_TIMEOUT)) {
            HAL_Delay(100);
            return HAL_ERROR; // or do a retry here
        }
    }
    return st;
}
*/



static HAL_StatusTypeDef i2c_read_4bytes(uint8_t addr, uint8_t cmd, uint8_t out[4]) {
    // Shift 7-bit address left by 1 for HAL
    uint8_t devAddr = (uint8_t)(addr << 1);
    HAL_StatusTypeDef st = HAL_I2C_Master_Transmit(&hi2c2, devAddr, &cmd, 1, I2C_TIMEOUT_MS);
    if (st != HAL_OK) return st;
    HAL_Delay(20); //Delay slave to prepare data
    st = HAL_I2C_Master_Receive(&hi2c2, devAddr, out, 4, I2C_TIMEOUT_MS);
    return st;
}

// Assemble float from little-endian 4 bytes

static float float_from_le_bytes(const uint8_t b[4]) {
    union { uint8_t b[4]; float f; } u;
    u.b[0] = b[0];
    u.b[1] = b[1];
    u.b[2] = b[2];
    u.b[3] = b[3];
    return u.f;
}


/* High-level: Get Load Value from specific address */
HAL_StatusTypeDef get_load_as_float(uint8_t addr, float *out) {
    uint8_t raw[4];
    HAL_StatusTypeDef st;

    // ------------ Attempt #1 ------------
    st = i2c_read_4bytes(addr, CMD_READ_LOAD, raw);
    if(st != HAL_OK) {
        // Hard error such as NACK -> try again after longer wait
        HAL_Delay(200);
        st = i2c_read_4bytes(addr, CMD_READ_LOAD, raw);
        if(st != HAL_OK) return st;
    }

    float f = float_from_le_bytes(raw);

    // Check for invalid float (INF / -INF / NaN)
    if(isinf(f) || isnan(f)) {
        // Conditional delay ONLY when invalid sample found
        HAL_Delay(200);

        // ------------ Attempt #2 (retry) ------------
        st = i2c_read_4bytes(addr, CMD_READ_LOAD, raw);
        if(st != HAL_OK) return st;

        f = float_from_le_bytes(raw);

        // If still invalid -> report error up
        if(isinf(f) || isnan(f)) {
            return HAL_ERROR;
        }
    }

    *out = f;
    return HAL_OK;
}

/* Manual Float Print Helper */
static void print_float_manual(float f, int precision)
{
    if (isnan(f)) { UART2_Printf("nan"); return; }
    if (isinf(f)) { UART2_Printf(f < 0.0f ? "-inf" : "inf"); return; }
    if (f < 0.0f) { UART2_Printf("-"); f = -f; }

    uint32_t ipart = (uint32_t)f;
    float fracf = f - (float)ipart;
    uint32_t mult = 1;
    for (int i = 0; i < precision; ++i) mult *= 10;

    float rounding = 0.5f / (float)mult;
    uint32_t frac = (uint32_t)((fracf + rounding) * (float)mult);
    if (frac >= mult) { ipart += 1; frac -= mult; }

    UART2_Printf("%lu", (unsigned long)ipart);
    if (precision > 0) {
        UART2_Printf(".");
        int digits = 0;
        uint32_t tmp = frac;
        if (frac == 0) digits = 1;
        else { while (tmp) { digits++; tmp /= 10; } }
        for (int i = 0; i < precision - digits; ++i) UART2_Printf("0");
        UART2_Printf("%lu", (unsigned long)frac);
    }
}

void start_motor(uint8_t slave_address, int16_t velocity) {
    uint8_t frame[8];

    // Note: The first byte (slave address) is now a variable.
    uint8_t en[]    = {slave_address, 0x06, 0x04, 0x05, 0x00, 0x83};
    uint8_t mode[]  = {slave_address, 0x06, 0x62, 0x00, 0x00, 0x02};
    uint8_t vel[]   = {slave_address, 0x06, 0x62, 0x03, (velocity >> 8), velocity & 0xFF};
    //uint8_t acc[]   = {slave_address, 0x06, 0x62, 0x04, (MOTOR_ACC_DEC >> 8), MOTOR_ACC_DEC & 0xFF};
    //uint8_t dec[]   = {slave_address, 0x06, 0x62, 0x05, (MOTOR_ACC_DEC >> 8), MOTOR_ACC_DEC & 0xFF};
    uint8_t start[] = {slave_address, 0x06, 0x60, 0x02, 0x00, 0x10};

    memcpy(frame, en, 6);    append_crc(frame, 6); modbus_send(frame, 8);
     memcpy(frame, mode, 6);  append_crc(frame, 6); modbus_send(frame, 8);
    memcpy(frame, vel, 6);   append_crc(frame, 6); modbus_send(frame, 8);
    /*memcpy(frame, acc, 6);   append_crc(frame, 6); modbus_send(frame, 8);
    memcpy(frame, dec, 6);   append_crc(frame, 6); modbus_send(frame, 8); */
    memcpy(frame, start, 6); append_crc(frame, 6); modbus_send(frame, 8);
}

/**
  * @brief  Stops a specific motor.
  * @param  slave_address: The Modbus slave address of the motor to stop.
  * @retval None
  */
void stop_motor(uint8_t slave_address) {
    uint8_t frame[8];

    uint8_t stop[] = {slave_address, 0x06, 0x60, 0x02, 0x00, 0x40};
    uint8_t dis[]  = {slave_address, 0x06, 0x04, 0x05, 0x00, 0x03};

    memcpy(frame, stop, 6); append_crc(frame, 6); modbus_send(frame, 8);
    memcpy(frame, dis, 6);  append_crc(frame, 6); modbus_send(frame, 8);
}

void handle_preload_logic(void) {
    if (current_state == STATE_IDLE) return;

    // Determine which indices to check based on state
    bool check_indices[4] = {false};

    if (current_state == STATE_PRELOAD_X) {
        check_indices[2] = true;
        check_indices[3] = true;
    }
    else if (current_state == STATE_PRELOAD_Y) {
        check_indices[0] = true;
        check_indices[1] = true;
    }
    else if (current_state == STATE_PRELOAD_ALL) {
        check_indices[0] = true;
        check_indices[1] = true;
        check_indices[2] = true;
        check_indices[3] = true;
    }

    bool all_targets_reached = true;

    // Loop through relevant motors
    for (int i = 0; i < 4; i++) {
        if (!check_indices[i]) continue;
        if (motor_target_reached[i]) continue;

        all_targets_reached = false;

        // Use non-blocking sensor data from sensor_loads[]
        float current_force = sensor_loads[i];

        if (current_force == 0.0f) {
            continue; // Skip if no valid reading yet
        }

        // Check Threshold
        bool threshold_met = false;
        if (target_preload_force > 0) {
            if (current_force >= target_preload_force) threshold_met = true;
        } else {
            if (current_force <= target_preload_force) threshold_met = true;
        }

        // Action
        if (threshold_met) {
            stop_motor(slave_addresses[i]);
            motor_target_reached[i] = true;
            UART2_Printf("Motor %d Target Reached (%.2f N)\r\n", i+1, current_force);
        }
    }

    // Exit Condition
    if (all_targets_reached) {
        UART2_Printf("Preload Complete. Switching to IDLE.\r\n");
        current_state = STATE_IDLE;
    }
}
/* Convert raw sensor value (kg) to kN and stop all motors if threshold exceeded.
   raw_load_kg should be the same units returned by get_load_as_float (kg).
   Conversion: kN = raw_load_kg * 9.8 / 1000

   NOISE FILTER: Requires 10 consecutive readings above threshold before triggering.
*/
#define OVERLOAD_CONSECUTIVE_COUNT 10  // Must exceed threshold this many times in a row

void handle_overload(float raw_load_kg, int sensor_index, int16_t motor_velocity)
{
    static int overload_count[4] = {0};  // Per-sensor counter

    float kn = raw_load_kg * 9.8f / 1000.0f;

    // Direction-aware overload: Only trigger if motor is LOADING (increasing force)
    // - Positive velocity + positive force = loading in compression
    // - Negative velocity + negative force = loading in tension
    // - Opposite signs = unloading and safe to run
    bool is_loading = (motor_velocity > 0 && kn > 0) || (motor_velocity < 0 && kn < 0);

    if (fabs(kn) > OVERLOAD_KN_THRESHOLD && is_loading) {
        overload_count[sensor_index]++;

        if (overload_count[sensor_index] >= OVERLOAD_CONSECUTIVE_COUNT) {
            UART2_Printf("OVERLOAD: LC%d = %.3f KN (threshold %.2f KN). Stopping ALL motors\r\n",
                         sensor_index + 1, kn, OVERLOAD_KN_THRESHOLD);

            /* Stop all motors using broadcast address */
            stop_motor(0x00);

            /* Move system to safe state */
            current_state = STATE_IDLE;

            /* Clear flags */
            for (int m = 0; m < 4; ++m) {
                motor_target_reached[m] = false;
                overload_count[m] = 0;  // Reset all counters
            }
        }
    } else {
        // Below threshold or unloading - reset this sensor's counter
        overload_count[sensor_index] = 0;
    }
}


/**
  * @brief  Parses UART commands and controls the motors.
  * @param  cmd: The null-terminated command string received via UART.
  * @retval None
  */
void process_command(char* cmd) {
    // --- Velocity Commands (Corrected with new standardized names) ---
    if (strncmp(cmd, "VEL1:", 5) == 0) {
        motor_velocities[0] = atoi(cmd + 5);
    } else if (strncmp(cmd, "VEL2:", 5) == 0) {
        motor_velocities[1] = atoi(cmd + 5);
    } else if (strncmp(cmd, "VEL3:", 5) == 0) {
        motor_velocities[2] = atoi(cmd + 5);
    } else if (strncmp(cmd, "VEL4:", 5) == 0) {
        motor_velocities[3] = atoi(cmd + 5);
    } else if (strncmp(cmd, "VELY:", 5) == 0) {
        int16_t v = atoi(cmd + 5);
        motor_velocities[0] = v; // Motor 1
        motor_velocities[1] = v; // Motor 2
    } else if (strncmp(cmd, "VELX:", 5) == 0) {
        int16_t v = atoi(cmd + 5);
        motor_velocities[2] = v; // Motor 3
        motor_velocities[3] = v; // Motor 4
    } else if (strncmp(cmd, "VEL:", 4) == 0) { // Global velocity
        int16_t v = atoi(cmd + 4);
        for(int i=0; i<4; i++) motor_velocities[i] = v;
    }

    // --- START Commands (These were already correct) ---
    else if (strcmp(cmd, "STARTM1") == 0) {
        start_motor(slave_addresses[0], motor_velocities[0]);
    } else if (strcmp(cmd, "STARTM2") == 0) {
        start_motor(slave_addresses[1], motor_velocities[1]);
    } else if (strcmp(cmd, "STARTM3") == 0) {
        start_motor(slave_addresses[2], motor_velocities[2]);
    } else if (strcmp(cmd, "STARTM4") == 0) {
        start_motor(slave_addresses[3], motor_velocities[3]);
    } else if (strcmp(cmd, "STARTY") == 0) {
        start_motor(slave_addresses[0], motor_velocities[0]);
        start_motor(slave_addresses[1], motor_velocities[1]);
    } else if (strcmp(cmd, "STARTX") == 0) {
        start_motor(slave_addresses[2], motor_velocities[2]);
        start_motor(slave_addresses[3], motor_velocities[3]);
    } else if (strcmp(cmd, "START") == 0) {
        for(int i=0; i<4; i++) {
            start_motor(0x00, motor_velocities[i]);
        }
    }

    // --- STOP Commands (These were already correct) ---
    else if (strcmp(cmd, "STOPM1") == 0) {
        stop_motor(slave_addresses[0]);
    } else if (strcmp(cmd, "STOPM2") == 0) {
        stop_motor(slave_addresses[1]);
    } else if (strcmp(cmd, "STOPM3") == 0) {
        stop_motor(slave_addresses[2]);
    } else if (strcmp(cmd, "STOPM4") == 0) {
        stop_motor(slave_addresses[3]);
    } else if (strcmp(cmd, "STOPY") == 0) {
        stop_motor(slave_addresses[0]);
        stop_motor(slave_addresses[1]);
    } else if (strcmp(cmd, "STOPX") == 0) {
        stop_motor(slave_addresses[2]);
        stop_motor(slave_addresses[3]);
    } else if (strcmp(cmd, "STOP") == 0) {
            stop_motor(0x00);

    }
    // --- Preload Commands ---
    else if (strncmp(cmd, "XPRE:", 5) == 0) {
            target_preload_force = atof(cmd + 5);
            current_state = STATE_PRELOAD_X;

            // Set Velocity based on direction
            current_preload_vel = (target_preload_force >= 0) ? PRELOAD_SPEED_RPM : -PRELOAD_SPEED_RPM;

            // Reset flags for X axis (Indices 2 & 3)
            motor_target_reached[2] = false;
            motor_target_reached[3] = false;

            UART2_Printf("Starting X Preload to %.2f N at %d RPM\r\n", target_preload_force, current_preload_vel);

            // Start Motors immediately
            start_motor(slave_addresses[2], current_preload_vel);
            start_motor(slave_addresses[3], current_preload_vel);
        }
        else if (strncmp(cmd, "YPRE:", 5) == 0) {
            target_preload_force = atof(cmd + 5);
            current_state = STATE_PRELOAD_Y;

            // Set Velocity based on direction
            current_preload_vel = (target_preload_force >= 0) ? PRELOAD_SPEED_RPM : -PRELOAD_SPEED_RPM;

            // Reset flags for Y axis (Indices 0 & 1)
            motor_target_reached[0] = false;
            motor_target_reached[1] = false;

            UART2_Printf("Starting Y Preload to %.2f N at %d RPM\r\n", target_preload_force, current_preload_vel);

            // Start Motors immediately
            start_motor(slave_addresses[0], current_preload_vel);
            start_motor(slave_addresses[1], current_preload_vel);
        }
    // --- NEW COMMAND: PRESTOP (Emergency Stop for Preload) ---
        if (strcmp(cmd, "PRESTOP") == 0) {
            current_state = STATE_IDLE; // Force state to IDLE

            // Stop all 4 motors immediately
            for(int i=0; i<4; i++) {
                stop_motor(slave_addresses[i]);
                motor_target_reached[i] = false; // Reset flags
            }
            UART2_Printf("PRELOAD STOPPED BY USER.\r\n");
        }

        else if (strncmp(cmd, "PRE:", 4) == 0) {
            target_preload_force = atof(cmd + 4);
            current_state = STATE_PRELOAD_ALL;

            // Set Velocity based on direction (+/- 40 RPM)
            current_preload_vel = (target_preload_force >= 0) ? PRELOAD_SPEED_RPM : -PRELOAD_SPEED_RPM;

            // Reset ALL flags
            for(int i=0; i<4; i++) {
                motor_target_reached[i] = false;
            }

            UART2_Printf("Starting ALL AXES Preload to %.2f N at %d RPM\r\n", target_preload_force, current_preload_vel);

            // Start ALL Motors immediately
            for(int i=0; i<4; i++) {
                start_motor(slave_addresses[i], current_preload_vel);
            }
        }
}
void check_kill_switch() {
	if(HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_5) == GPIO_PIN_RESET)
	{
		kill_switch_triggered=true;
		 UART2_Printf("KILLSWITCH TRIGGERED! Stopping all motors.\r\n");
	}

}
/* Helper Functions ----------------------------------------------------------*/
void UART2_Printf(const char *format, ...)
{
    char buffer[128];
    va_list args;
    va_start(args, format);
    int len = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);

    if (len <= 0) return;

    /* Use a finite timeout so we don't block indefinitely (avoid HAL_MAX_DELAY) */
    uint32_t timeout_ms = 20; /* adjust to 50-200 ms depending on console speed */
    HAL_StatusTypeDef st = HAL_UART_Transmit(&huart2, (uint8_t*)buffer, (uint16_t)len, timeout_ms);

    /* Optional: If transmit fails, you can ignore (we don't want to block)
       or set a flag for occasional logging. Do not call HAL inside ISR. */
    (void)st;
}

void Print_Debug_Hex(char* prefix, uint8_t *frame, uint16_t len) {
    char buffer[128];
    int offset = 0;
    offset += snprintf(buffer + offset, sizeof(buffer) - offset, "%s (ID=%02X): ", prefix, frame[0]);
    for (int i = 0; i < len; i++) {
        if (offset >= sizeof(buffer) - 5) break;
        offset += snprintf(buffer + offset, sizeof(buffer) - offset, "%02X ", frame[i]);
    }
    snprintf(buffer + offset, sizeof(buffer) - offset, "\r\n");
    HAL_UART_Transmit(&huart2, (uint8_t*)buffer, strlen(buffer), 100);
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

void print_modbus_frame(uint8_t* frame, uint16_t len) {
    char msg[100];
    int pos = 0;
    pos += snprintf(msg + pos, sizeof(msg) - pos, "Sent to %02X: ", frame[0]);
    for (uint16_t i = 0; i < len; i++) {
        pos += snprintf(msg + pos, sizeof(msg) - pos, "%02X ", frame[i]);
    }
    pos += snprintf(msg + pos, sizeof(msg) - pos, "\r\n");
    HAL_UART_Transmit(&huart2, (uint8_t*)msg, pos, HAL_MAX_DELAY);
}

void append_crc(uint8_t *frame, uint16_t len) {
    uint16_t crc = modbus_crc(frame, len);
    frame[len] = crc & 0xFF;
    frame[len + 1] = (crc >> 8);
}

// --- NON-BLOCKING MODBUS IMPLEMENTATION ---
void Modbus_Enqueue(uint8_t *frame, uint16_t len) {
    if (mb_count >= MB_QUEUE_SIZE) {
        return;  // Queue full, drop frame
    }
    memcpy(mb_tx_queue[mb_head], frame, 8);
    mb_head = (mb_head + 1) % MB_QUEUE_SIZE;
    __disable_irq();
    mb_count++;
    __enable_irq();
}

void Modbus_Process(void) {
    switch (mb_state) {
        case MB_IDLE:
            if (mb_count > 0) {
                // Start transmitting next frame
                if (HAL_UART_Transmit_IT(&huart1, mb_tx_queue[mb_tail], 8) == HAL_OK) {
                    mb_state = MB_TX_IN_PROGRESS;
                }
            }
            break;

        case MB_TX_IN_PROGRESS:
            // Waiting for TxCpltCallback to fire
            break;

        case MB_WAITING_GAP:
            // Wait for inter-frame gap
            if (HAL_GetTick() - mb_gap_start >= MB_INTER_FRAME_GAP_MS) {
                mb_state = MB_IDLE;  // Ready for next frame
            }
            break;
    }
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance == USART1) {
        // Frame sent, advance queue
        mb_tail = (mb_tail + 1) % MB_QUEUE_SIZE;
        __disable_irq();
        if (mb_count > 0) mb_count--;
        __enable_irq();

        // Start inter-frame gap
        mb_gap_start = HAL_GetTick();
        mb_state = MB_WAITING_GAP;
    }
}

// Wrapper for compatibility - now queues instead of blocking
void modbus_send(uint8_t *frame, uint16_t len) {
    Modbus_Enqueue(frame, len);
}

// --- NON-BLOCKING I2C SENSOR SCAN ---
void I2C_Scan_Start(void) {
    if (i2c_state == I2C_IDLE) {
        i2c_current_sensor = 0;
        sensor_scan_complete = false;
        i2c_state = I2C_TX_CMD;
    }
}

void I2C_Scan_Process(void) {
    static uint8_t cmd_byte = CMD_READ_LOAD;

    switch (i2c_state) {
        case I2C_IDLE:
            // Do nothing, waiting for I2C_Scan_Start()
            break;

        case I2C_TX_CMD:
            // Send command to current sensor
            {
                uint8_t addr = lc_slave_addresses[i2c_current_sensor];
                if (HAL_I2C_Master_Transmit_IT(&hi2c2, addr << 1, &cmd_byte, 1) == HAL_OK) {
                    i2c_state = I2C_WAIT_DELAY;
                    i2c_delay_start = HAL_GetTick();
                }
            }
            break;

        case I2C_WAIT_DELAY:
            // Wait for sensor to prepare data
            if (HAL_GetTick() - i2c_delay_start >= 200) {
                uint8_t addr = lc_slave_addresses[i2c_current_sensor];
                HAL_I2C_Master_Abort_IT(&hi2c2, addr << 1);
                sensor_loads[i2c_current_sensor] = 0.0f; // Unmask timeout error
                i2c_current_sensor++;
                if (i2c_current_sensor >= num_sensors) {
                    i2c_state = I2C_IDLE;
                    sensor_scan_complete = true;
                } else {
                    i2c_state = I2C_TX_CMD;
                }
            } else if (HAL_GetTick() - i2c_delay_start >= I2C_RESPONSE_DELAY_MS) {
                uint8_t addr = lc_slave_addresses[i2c_current_sensor];
                if (HAL_I2C_Master_Receive_IT(&hi2c2, addr << 1, i2c_raw_data, 4) == HAL_OK) {
                    i2c_state = I2C_RX_DATA;
                }
            }
            break;

        case I2C_RX_DATA:
            // Waiting for RxCpltCallback to fire
            if (HAL_GetTick() - i2c_delay_start >= 200) {
                uint8_t addr = lc_slave_addresses[i2c_current_sensor];
                HAL_I2C_Master_Abort_IT(&hi2c2, addr << 1);
                sensor_loads[i2c_current_sensor] = 0.0f; // Unmask timeout error
                i2c_current_sensor++;
                if (i2c_current_sensor >= num_sensors) {
                    i2c_state = I2C_IDLE;
                    sensor_scan_complete = true;
                } else {
                    i2c_state = I2C_TX_CMD;
                }
            }
            break;

        case I2C_WAIT_READY:
            // Reserved for error recovery
            break;
    }
}

void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *hi2c) {
    // TX complete is handled by state machine timing
    (void)hi2c;
}

void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *hi2c) {
    if (hi2c->Instance == I2C2) {
        // Parse received data
        union { uint8_t b[4]; float f; } u;
        u.b[0] = i2c_raw_data[0];
        u.b[1] = i2c_raw_data[1];
        u.b[2] = i2c_raw_data[2];
        u.b[3] = i2c_raw_data[3];

        float val = u.f;
        if (!isinf(val) && !isnan(val)) {
            sensor_loads[i2c_current_sensor] = val;
        } else {
            sensor_loads[i2c_current_sensor] = 0.0f; // Unmask corrupted/NaN data error
        }

        // Move to next sensor
        i2c_current_sensor++;
        if (i2c_current_sensor >= num_sensors) {
            i2c_state = I2C_IDLE;
            sensor_scan_complete = true;
        } else {
            i2c_state = I2C_TX_CMD;
        }
    }
}

void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c) {
    if (hi2c->Instance == I2C2) {
        // Skip to next sensor on error
        sensor_loads[i2c_current_sensor] = 0.0f;
        i2c_current_sensor++;
        if (i2c_current_sensor >= num_sensors) {
            i2c_state = I2C_IDLE;
            sensor_scan_complete = true;
        } else {
            i2c_state = I2C_TX_CMD;
        }
    }
}



void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance == USART2) {
        if (uart2_byte == '\n' || uart2_byte == '\r') {
            if (rx_index > 0) { // if a command is present
                uart2_rx_buf[rx_index] = '\0'; // Null-terminate

                // Enqueue command into circular buffer
                __disable_irq();
                if (cmd_queue_count < CMD_QUEUE_SIZE) {
                    strncpy(cmd_queue[cmd_queue_head], uart2_rx_buf, MAX_CMD_LEN);
                    cmd_queue[cmd_queue_head][MAX_CMD_LEN-1] = '\0';
                    cmd_queue_head = (cmd_queue_head + 1) % CMD_QUEUE_SIZE;
                    cmd_queue_count++;
                }
                // else: queue full, command dropped (optional: add overflow flag)
                __enable_irq();

                rx_index = 0; // clear assembly buffer
            }
        } else if (rx_index < MAX_CMD_LEN - 1) {
            uart2_rx_buf[rx_index++] = uart2_byte; // Append character
        }
        // Re-arm receive interrupt for the next byte
        HAL_UART_Receive_IT(&huart2, &uart2_byte, 1);
    }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
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
  MX_I2C2_Init();
  MX_USART1_UART_Init();
  MX_I2C1_Init();
  /* USER CODE BEGIN 2 */
  HAL_UART_Receive_IT(&huart2, &uart2_byte, 1); // Start UART RX interrupt
/*
  // Wait for motor drivers to power up (blocking only at startup)
  uint32_t boot_start = HAL_GetTick();
  while (HAL_GetTick() - boot_start < 3000) {
      // Spin wait at boot only
  }
*/
  // Send initialization frames to all motors
  uint8_t frame[8];
  for (int i = 0; i < 4; i++) {
      uint8_t acc[]   = {slave_addresses[i], 0x06, 0x62, 0x04, (MOTOR_ACC_DEC >> 8), MOTOR_ACC_DEC & 0xFF};
      uint8_t dec[]   = {slave_addresses[i], 0x06, 0x62, 0x05, (MOTOR_ACC_DEC >> 8), MOTOR_ACC_DEC & 0xFF};
      memcpy(frame, acc, 6);   append_crc(frame, 6); modbus_send(frame, 8);
      memcpy(frame, dec, 6);   append_crc(frame, 6); modbus_send(frame, 8);
  }

  // Wait for init frames to be sent before entering main loop
  while (mb_count > 0) {
      Modbus_Process();
  }

  // Start first sensor scan
  I2C_Scan_Start();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
	     if (kill_switch_triggered) {
	    	    	            stop_motor(0x00);
	    	    	                kill_switch_triggered = false;
	    	    	            }
	    	    	        check_kill_switch();
      // 1. Process Modbus TX queue (non-blocking)
      Modbus_Process();

      // 2. Process I2C sensor scan (non-blocking)
      I2C_Scan_Process();

      // 3. Process incoming UART commands
      if (cmd_queue_count > 0) {
          char local_cmd[MAX_CMD_LEN];
          __disable_irq();
          strncpy(local_cmd, cmd_queue[cmd_queue_tail], MAX_CMD_LEN);
          cmd_queue_tail = (cmd_queue_tail + 1) % CMD_QUEUE_SIZE;
          cmd_queue_count--;
          __enable_irq();
          process_command(local_cmd);
      }

      // 4. Handle preload logic when active
      if (current_state != STATE_IDLE) {
          handle_preload_logic();
      }

      // 5. Output sensor data when scan is complete
      if (sensor_scan_complete) {
          sensor_scan_complete = false;

          // Check overload (direction-aware: pass motor velocity) - only for valid readings
          for (int i = 0; i < num_sensors; i++) {
              if (sensor_loads[i] != 0.0f) {
                  handle_overload(sensor_loads[i], i, motor_velocities[i]);
              }
          }

          // Output CSV: load1,load2,load3,load4 (or ERR for failed sensors)
          for (int i = 0; i < num_sensors; i++) {
              if (sensor_loads[i] == 0.0f) {
                  UART2_Printf("ERR");  // Error marker for failed sensor
              } else {
                  float kn = sensor_loads[i] * 9.8f / 1000.0f;
                  print_float_manual(kn, 3);
              }
              if (i < num_sensors - 1) UART2_Printf(",");
          }
          UART2_Printf("\r\n");

          // Start next scan
          I2C_Scan_Start();
      }


	     // HAL_Delay(1);


  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
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
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{

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
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C1_Init 2 */

  /* USER CODE END I2C1_Init 2 */

}

/**
  * @brief I2C2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C2_Init(void)
{

  /* USER CODE BEGIN I2C2_Init 0 */

  /* USER CODE END I2C2_Init 0 */

  /* USER CODE BEGIN I2C2_Init 1 */

  /* USER CODE END I2C2_Init 1 */
  hi2c2.Instance = I2C2;
  hi2c2.Init.ClockSpeed = 100000;
  hi2c2.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c2.Init.OwnAddress1 = 0;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.OwnAddress2 = 0;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C2_Init 2 */

  /* USER CODE END I2C2_Init 2 */

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_2;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
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
static void MX_USART2_UART_Init(void)
{

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
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
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
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0|LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : PA0 */
  GPIO_InitStruct.Pin = GPIO_PIN_0;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : PB4 PB5 */
  GPIO_InitStruct.Pin = GPIO_PIN_4|GPIO_PIN_5;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
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
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
