#!/usr/bin/env python3

import glob
import os
import os.path
import shutil
import subprocess
import sys

SYSROOT_NAME = 'sysroot'
LLVM_HEADERS_PATH = os.path.realpath(
    "../llvm-project/llvm-prefix/lib/clang/19/include")
TOOLCHAIN_BIN_PATH = '/Users/rqou/code/llvm-project/build-native/bin'
COMPILER_RT_LOCATION = os.path.realpath("../llvm-project/compiler-rt")
CXX_RUNTIMES_LOCATION = os.path.realpath("../llvm-project/runtimes")
PICOLIBC_LOCATION = os.path.realpath("../picolibc")
WASI_LIBC_LOCATION = os.path.realpath("../wasi-libc")

# We are *deliberately* using marketing names here, because we only want to support chips that are common "in the wild"
CPU_VARIANTS = [
    'wasi',

    'cortex-m01',
    'cortex-m3',
    'cortex-m4',
    'cortex-m4f',

    'qingke-v2a',
    'qingke-v34a',
    'qingke-v4bc',
    'qingke-v4f',
]

TARGET_TRIPLES = {
    'wasi': 'wasm32-wasip1',

    'cortex-m01': 'armv6m-unknown-none-eabi',
    'cortex-m3': 'armv7m-unknown-none-eabi',
    'cortex-m4': 'armv7em-unknown-none-eabi',
    'cortex-m4f': 'armv7em-unknown-none-eabihf',

    'qingke-v2a': 'riscv32-unknown-none-elf',
    'qingke-v34a': 'riscv32-unknown-none-elf',
    'qingke-v4bc': 'riscv32-unknown-none-elf',
    'qingke-v4f': 'riscv32-unknown-none-elf',
}

MULTILIB_PATHS = {
    'wasi': 'wasm32-wasip1',

    'cortex-m01': 'cm01',
    'cortex-m3': 'cm3',
    'cortex-m4': 'cm4',
    'cortex-m4f': 'cm4f',

    'qingke-v2a': "qk-v2a",
    'qingke-v34a': "qk-v34a",
    'qingke-v4bc': "qk-v4bc",
    'qingke-v4f': "qk-v4f",
}

TARGET_FLAGS = {
    'wasi': [],

    'cortex-m01': ['-march=armv6m', '-mfloat-abi=soft', '-mfpu=none'],
    'cortex-m3': ['-march=armv7m', '-mfloat-abi=soft', '-mfpu=none'],
    'cortex-m4': ['-march=armv7em', '-mfloat-abi=soft', '-mfpu=none'],
    # We deliberately don't support softfp, don't really see the point
    'cortex-m4f': ['-march=armv7em', '-mfloat-abi=hard', '-mfpu=fpv4-sp-d16'],

    'qingke-v2a': ['-march=rv32ec_xwchc'],
    'qingke-v34a': ['-march=rv32imac'],
    'qingke-v4bc': ['-march=rv32imac_xwchc'],
    'qingke-v4f': ['-march=rv32imafc_xwchc', '-mabi=ilp32f'],
}
COMMON_FLAGS = ['-ffunction-sections', '-fdata-sections', '-fno-ident']

MESON_CPUS = {
    'wasi': 'wasm32',

    'cortex-m01': 'arm',
    'cortex-m3': 'arm',
    'cortex-m4': 'arm',
    'cortex-m4f': 'arm',

    'qingke-v2a': 'riscv32',
    'qingke-v34a': 'riscv32',
    'qingke-v4bc': 'riscv32',
    'qingke-v4f': 'riscv32',
}


def make_cmake_toolchain(cpu):
    sysroot = os.path.realpath(SYSROOT_NAME)
    if cpu == 'wasi':
        sysroot += '/wasm32-wasip1'

    fn = os.path.realpath(f'Toolchain-{cpu}.cmake')

    triple = TARGET_TRIPLES[cpu]
    flags = ' '.join(TARGET_FLAGS[cpu] + COMMON_FLAGS)
    cmake_cpu = triple.split('-')[0]

    if cpu == 'wasi':
        wasi_extra = """
set(WASI TRUE)
set(CMAKE_EXECUTABLE_SUFFIX ".wasm")
"""
    else:
        wasi_extra = ""

    with open(fn, 'w') as f:
        f.write(f"""
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_VERSION 1)
set(CMAKE_SYSTEM_PROCESSOR {cmake_cpu})

{wasi_extra}

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(CMAKE_C_COMPILER {TOOLCHAIN_BIN_PATH}/clang)
set(CMAKE_CXX_COMPILER {TOOLCHAIN_BIN_PATH}/clang++)
set(CMAKE_LINKER {TOOLCHAIN_BIN_PATH}/ld.lld)
set(CMAKE_AR {TOOLCHAIN_BIN_PATH}/llvm-ar)
set(CMAKE_RANLIB {TOOLCHAIN_BIN_PATH}/llvm-ranlib)

set(CMAKE_ASM_COMPILER_TARGET {triple})
set(CMAKE_C_COMPILER_TARGET {triple})
set(CMAKE_CXX_COMPILER_TARGET {triple})
set(CMAKE_ASM_FLAGS "--sysroot {sysroot} {flags}")
set(CMAKE_C_FLAGS "--sysroot {sysroot} {flags}")
set(CMAKE_CXX_FLAGS "--sysroot {sysroot} {flags}")
set(CMAKE_EXE_LINKER_FLAGS "")
""")


def make_meson_toolchain(cpu):
    sysroot = os.path.realpath("sysroot")
    fn = os.path.realpath(f'meson-cross-{cpu}.txt')

    triple = TARGET_TRIPLES[cpu]
    flags = ','.join((f"'{x}'" for x in TARGET_FLAGS[cpu] + COMMON_FLAGS))
    meson_cpu = MESON_CPUS[cpu]

    with open(fn, 'w') as f:
        f.write(f"""
[binaries]
c = ['{TOOLCHAIN_BIN_PATH}/clang', '--sysroot',
    '{sysroot}', '--target={triple}', {flags}, '-nostdlib']
ar = '{TOOLCHAIN_BIN_PATH}/llvm-ar'
strip = '{TOOLCHAIN_BIN_PATH}/llvm-strip'

[host_machine]
system = 'none'
cpu_family = '{meson_cpu}'
cpu = '{meson_cpu}'
endian = 'little'

[properties]
skip_sanity_check = true
libgcc ='-lclang_rt.builtins'

""")


def build_compiler_rt(cpu):
    sysroot = os.path.realpath(SYSROOT_NAME)
    cmake_toolchain = os.path.realpath(f'Toolchain-{cpu}.cmake')
    build_dir = f"build-compiler-rt-{cpu}"
    multilib_path = MULTILIB_PATHS[cpu]
    shutil.rmtree(build_dir, ignore_errors=True)

    subprocess.run(["cmake", "-G", "Ninja",
                    "-S", COMPILER_RT_LOCATION,
                    "-B", build_dir,
                    f"-DCMAKE_TOOLCHAIN_FILE={cmake_toolchain}",
                    "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
                    "-DCOMPILER_RT_BAREMETAL_BUILD=ON",
                    "-DCOMPILER_RT_BUILD_LIBFUZZER=OFF",
                    "-DCOMPILER_RT_BUILD_PROFILE=OFF",
                    "-DCOMPILER_RT_BUILD_SANITIZERS=OFF",
                    "-DCOMPILER_RT_BUILD_MEMPROF=OFF",
                    "-DCOMPILER_RT_BUILD_ORC=OFF",
                    "-DCOMPILER_RT_BUILD_XRAY=OFF",
                    "-DCOMPILER_RT_INCLUDE_TESTS=OFF",
                    "-DCOMPILER_RT_HAS_FPIC_FLAG=OFF",
                    "-DCOMPILER_RT_ENABLE_IOS=OFF",
                    "-DCOMPILER_RT_DEFAULT_TARGET_ONLY=ON",
                    "-DLLVM_ENABLE_PER_TARGET_RUNTIME_DIR=ON",
                    f"-DCMAKE_INSTALL_PREFIX={sysroot}/{multilib_path}",
                    ], check=True)
    subprocess.run(["cmake", "--build", build_dir,
                   "--target", "install"], check=True)

    if cpu != 'wasi':
        # XXX don't know how to convice this otherwise
        compiler_rt_file = glob.glob(
            f"{SYSROOT_NAME}/{multilib_path}/lib/*/libclang_rt.builtins.a")
        assert len(compiler_rt_file) == 1
        compiler_rt_file = compiler_rt_file[0]
        os.rename(compiler_rt_file,
                  f"{SYSROOT_NAME}/{multilib_path}/lib/libclang_rt.builtins.a")
        os.rmdir(os.path.dirname(compiler_rt_file))


def build_wasi_libc():
    triple = TARGET_TRIPLES['wasi']
    sysroot = os.path.realpath(SYSROOT_NAME)
    multilib_path = MULTILIB_PATHS['wasi']
    subprocess.run(["make", "-C", WASI_LIBC_LOCATION,
                    f"CC={TOOLCHAIN_BIN_PATH}/clang",
                    f"AR={TOOLCHAIN_BIN_PATH}/llvm-ar",
                    f"NM={TOOLCHAIN_BIN_PATH}/llvm-nm",
                    f"TARGET_TRIPLE={triple}",
                    f"SYSROOT={sysroot}/{multilib_path}",
                    "-j8"
                    ], check=True)


def build_picolibc(cpu):
    sysroot = os.path.realpath(SYSROOT_NAME)
    meson_toolchain = os.path.realpath(f'meson-cross-{cpu}.txt')
    build_dir = f"build-picolibc-{cpu}"
    multilib_path = MULTILIB_PATHS[cpu]
    shutil.rmtree(build_dir, ignore_errors=True)
    subprocess.run(["meson", "setup",
                    f"-Dincludedir=include",
                    f"-Dlibdir=lib",
                    "-Dspecsdir=none",
                    "-Dmultilib=false",
                    "--prefix", f"{sysroot}/{multilib_path}",
                    "--cross-file", meson_toolchain,
                    "--buildtype=minsize",
                    PICOLIBC_LOCATION,
                    build_dir
                    ], check=True)
    subprocess.run(["ninja", "-C", build_dir, "install"], check=True)


def build_wasi_cxx():
    sysroot = os.path.realpath(SYSROOT_NAME)
    cmake_toolchain = os.path.realpath(f'Toolchain-wasi.cmake')
    build_dir = f"build-libcxx-wasi"
    shutil.rmtree(build_dir, ignore_errors=True)

    subprocess.run(["cmake", "-G", "Ninja",
                    "-S", CXX_RUNTIMES_LOCATION,
                    "-B", build_dir,
                    f"-DCMAKE_TOOLCHAIN_FILE={cmake_toolchain}",
                    "-DCMAKE_BUILD_TYPE=MinSizeRel",
                    "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
                    "-DLLVM_ENABLE_RUNTIMES:STRING=libcxx;libcxxabi",
                    "-DLIBCXX_ENABLE_THREADS:BOOL=OFF",
                    "-DLIBCXX_BUILD_EXTERNAL_THREAD_LIBRARY:BOOL=OFF",
                    "-DLIBCXX_ENABLE_SHARED:BOOL=OFF",
                    "-DLIBCXX_ENABLE_EXCEPTIONS:BOOL=OFF",
                    "-DLIBCXX_ENABLE_FILESYSTEM:BOOL=ON",
                    "-DLIBCXX_ENABLE_EXPERIMENTAL_LIBRARY:BOOL=OFF",
                    "-DLIBCXX_ENABLE_ABI_LINKER_SCRIPT:BOOL=OFF",
                    "-DLIBCXX_CXX_ABI=libcxxabi",
                    "-DLIBCXX_HAS_MUSL_LIBC:BOOL=ON",
                    "-DLIBCXX_ABI_VERSION=2",
                    "-DLIBCXXABI_ENABLE_THREADS:BOOL=OFF",
                    "-DLIBCXXABI_BUILD_EXTERNAL_THREAD_LIBRARY:BOOL=OFF",
                    "-DLIBCXXABI_ENABLE_PIC:BOOL=OFF",
                    "-DLIBCXXABI_ENABLE_SHARED:BOOL=OFF",
                    "-DLIBCXXABI_ENABLE_EXCEPTIONS:BOOL=OFF",
                    "-DLIBCXXABI_USE_LLVM_UNWINDER:BOOL=OFF",
                    "-DLIBCXXABI_SILENT_TERMINATE:BOOL=ON",
                    "-DLIBCXX_LIBDIR_SUFFIX=/wasm32-wasip1",
                    "-DLIBCXXABI_LIBDIR_SUFFIX=/wasm32-wasip1",
                    f"-DCMAKE_INSTALL_PREFIX={sysroot}/wasm32-wasip1",
                    ], check=True)
    subprocess.run(["cmake", "--build", build_dir,
                   "--target", "install"], check=True)


def build_cxx(cpu, enable_exceptions, enable_rtti):
    variant = "-"
    if enable_exceptions:
        variant += "exc-"
    else:
        variant += "noexc-"
    if enable_rtti:
        variant += "rtti"
    else:
        variant += "nortti"

    if enable_exceptions:
        enable_exceptions_str = "ON"
    else:
        enable_exceptions_str = "OFF"
    if enable_rtti:
        enable_rtti_str = "ON"
    else:
        enable_rtti_str = "OFF"

    sysroot = os.path.realpath(SYSROOT_NAME)
    cmake_toolchain = os.path.realpath(f'Toolchain-{cpu}.cmake')
    build_dir = f"build-libcxx-{cpu}{variant}"
    multilib_path = MULTILIB_PATHS[cpu]
    shutil.rmtree(build_dir, ignore_errors=True)

    subprocess.run(["cmake", "-G", "Ninja",
                    "-S", CXX_RUNTIMES_LOCATION,
                    "-B", build_dir,
                    f"-DCMAKE_TOOLCHAIN_FILE={cmake_toolchain}",
                    "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
                    "-DLIBCXXABI_BAREMETAL=ON",
                    "-DLIBCXXABI_ENABLE_ASSERTIONS=OFF",
                    "-DLIBCXXABI_ENABLE_SHARED=OFF",
                    "-DLIBCXXABI_ENABLE_STATIC=ON",
                    "-DLIBCXXABI_USE_COMPILER_RT=ON",
                    "-DLIBCXXABI_USE_LLVM_UNWINDER=ON",
                    "-DLIBCXX_ABI_UNSTABLE=ON",
                    "-DLIBCXX_CXX_ABI=libcxxabi",
                    "-DLIBCXX_ENABLE_FILESYSTEM=OFF",
                    "-DLIBCXX_ENABLE_SHARED=OFF",
                    "-DLIBCXX_ENABLE_STATIC=ON",
                    "-DLIBCXX_INCLUDE_BENCHMARKS=OFF",
                    "-DLIBUNWIND_ENABLE_SHARED=OFF",
                    "-DLIBUNWIND_ENABLE_STATIC=ON",
                    "-DLIBUNWIND_IS_BAREMETAL=ON",
                    "-DLIBUNWIND_REMEMBER_HEAP_ALLOC=ON",
                    "-DLIBUNWIND_USE_COMPILER_RT=ON",
                    "-DLLVM_ENABLE_RUNTIMES=libcxxabi;libcxx;libunwind",
                    "-DLIBCXXABI_ENABLE_THREADS=OFF",
                    "-DLIBCXX_ENABLE_MONOTONIC_CLOCK=OFF",
                    "-DLIBCXX_ENABLE_RANDOM_DEVICE=OFF",
                    "-DLIBCXX_ENABLE_THREADS=OFF",
                    "-DLIBCXX_ENABLE_WIDE_CHARACTERS=OFF",
                    "-DLIBUNWIND_ENABLE_THREADS=OFF",
                    f"-DLIBCXXABI_ENABLE_EXCEPTIONS={enable_exceptions_str}",
                    f"-DLIBCXXABI_ENABLE_STATIC_UNWINDER={enable_exceptions_str}",      # noqa
                    f"-DLIBCXX_ENABLE_EXCEPTIONS={enable_exceptions_str}",
                    f"-DLIBCXX_ENABLE_RTTI={enable_rtti_str}",
                    f"-DCMAKE_INSTALL_PREFIX={sysroot}/{multilib_path}{variant}",    # noqa
                    ], check=True)
    subprocess.run(["cmake", "--build", build_dir,
                   "--target", "install"], check=True)


def build_for_cpu(cpu):
    print(f"Building for CPU \"{cpu}\"!")
    make_cmake_toolchain(cpu)
    if cpu != 'wasi':
        make_meson_toolchain(cpu)
    build_compiler_rt(cpu)

    if cpu == 'wasi':
        build_wasi_libc()
        build_wasi_cxx()
    else:
        build_picolibc(cpu)
        for (enable_exceptions, enable_rtti) in [(False, False), (False, True), (True, True)]:
            build_cxx(cpu, enable_exceptions, enable_rtti)


def make_multilib_yaml():
    with open(f"{SYSROOT_NAME}/multilib.yaml", 'w') as f:
        f.write("MultilibVersion: 1.0\n")

        f.write("Groups:\n")
        f.write("- Name: c_libs\n")
        f.write("  Type: Exclusive\n")
        for cpu in CPU_VARIANTS:
            if cpu == 'wasi':
                continue
            multilib_dir_name = MULTILIB_PATHS[cpu]
            f.write(f"- Name: {multilib_dir_name}_cxx_libs\n")
            f.write("  Type: Exclusive\n")

        f.write("Variants:\n")
        for cpu in CPU_VARIANTS:
            if cpu == 'wasi':
                continue
            multilib_dir_name = MULTILIB_PATHS[cpu]
            triple = TARGET_TRIPLES[cpu]
            flags = TARGET_FLAGS[cpu]
            if triple.startswith("arm"):
                # XXX ugly
                triple = "thumb" + triple[3:]
                flags = [x for x in flags if not x.startswith("-march=")]
            flags = [f'--target={triple}'] + flags
            flags_str = ','.join((f"'{x}'" for x in flags))

            f.write(f"- Dir: {multilib_dir_name}\n")
            f.write(f"  Flags: [{flags_str}]\n")
            f.write("  Group: c_libs\n")

            for (enable_exceptions, enable_rtti) in [(False, False), (False, True), (True, True)]:
                variant = "-"
                flags2 = list(flags)
                if enable_exceptions:
                    variant += "exc-"
                    flags2.append("-fexceptions")
                else:
                    variant += "noexc-"
                    flags2.append("-fno-exceptions")
                if enable_rtti:
                    variant += "rtti"
                    flags2.append("-frtti")
                else:
                    variant += "nortti"
                    flags2.append("-fno-rtti")
                flags_str = ','.join((f"'{x}'" for x in flags2))

                f.write(f"- Dir: {multilib_dir_name}{variant}\n")
                f.write(f"  Flags: [{flags_str}]\n")
                f.write(f"  Group: {multilib_dir_name}_cxx_libs\n")

        f.write("Mappings:\n")
        f.write("- Match: \"-mfloat-abi=softfp\"\n")
        f.write("  Flags: [\"-mfloat-abi=soft\"]\n")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "clean":
        print("CLEAN!")
        for x in glob.glob("build-*"):
            shutil.rmtree(x, ignore_errors=True)
        for x in glob.glob("meson-cross-*.txt"):
            os.remove(x)
        for x in glob.glob("Toolchain-*.cmake"):
            os.remove(x)
        shutil.rmtree(SYSROOT_NAME, ignore_errors=True)
        return

    if not os.path.exists(SYSROOT_NAME):
        os.makedirs(SYSROOT_NAME)
    make_multilib_yaml()
    for cpu in CPU_VARIANTS:
        build_for_cpu(cpu)
    shutil.copytree(LLVM_HEADERS_PATH,
                    "sysroot/include", dirs_exist_ok=True)
    shutil.copytree(LLVM_HEADERS_PATH,
                    "sysroot/wasm32-wasip1/include", dirs_exist_ok=True)


if __name__ == '__main__':
    main()
