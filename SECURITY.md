# Security

MotionProof is a local, single-user engineering tool. It has no authentication; run it bound to
`127.0.0.1` (the default) and do not expose it to a network.

* Uploads are limited to 300 MB (CAD) and 50 MB (measurements), stored under sanitised names,
  and never executed. No CAD macros or scripts are run.
* Paths inside a model directory are resolved and refused if they leave it.
* No shell commands are built from user input.
* Project deletion requires the project id as explicit confirmation.
* The optional AI assistant talks only to a local Ollama server and receives a digest of stored
  results; disable it with `MOTIONPROOF_AI=off`.
* MotionProof does not connect to actuators or other hardware.

Report problems to the project owner privately before publishing details.
