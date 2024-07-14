# Toolchain build nonsense

This builds runtime libraries for the targets we care about supporting:

* WASI
* Cortex-M microcontrollers
* WCH RISC-V microcontrollers

This is specifically designed to *not* be written in CMake.

## Shamelessly stolen from

* [YoWASP](https://github.com/YoWASP/clang)
* [wasi-sdk](https://github.com/WebAssembly/wasi-sdk)
* [LLVM embedded toolchain for Arm](https://github.com/ARM-software/LLVM-embedded-toolchain-for-Arm)
