# Device protocol (version 1)

Transport: USB serial or UART, 115200 baud, 8N1; one UTF-8 JSON object per line (`\n`).

## Device to host

```json
{"type":"hello","device":"RIG-01","firmware":"1.0.0","sensors":{"input_encoder_counts":4096,"output_encoder_counts":4096,"torque":false,"current":false,"temperature":true}}
{"type":"telemetry","seq":123,"t_us":615000,"command_rad":1.5708,"input_angle_rad":51.83,"output_angle_rad":1.5662,"input_counts":33790,"output_counts":1021,"torque_nm":null,"current_a":null,"temp_c":31.5,"flags":0}
```

| Field | Unit | Notes |
|---|---|---|
| `seq` | - | increments by 1; gaps count as lost packets |
| `t_us` | microseconds | device clock since the move started |
| `command_rad` | rad at the output | |
| `input_angle_rad` | rad, motor angle referred to the output | |
| `output_angle_rad` | rad at the output | |
| `torque_nm`, `current_a`, `temp_c` | N*m, A, deg C | `null` when not instrumented |
| `flags` | bit field | 0 emergency stop, 1 limit switch, 2 driver fault, 3 sensor fault |

Sampling: 100 to 1000 Hz recommended. Required fields that are missing, non-numeric or
non-finite make the line invalid; three invalid readings abort the test.

## Host to device

`{"cmd":"ping"}` (device answers with hello), `{"cmd":"arm"}`, `{"cmd":"move","test":{...}}`
with the `HardwareTest` fields, `{"cmd":"stop"}`. A device must refuse `move` unless armed and
must stop on its own if no command arrives for a firmware-defined period.

No firmware is provided; this protocol has not been implemented on a microcontroller.
