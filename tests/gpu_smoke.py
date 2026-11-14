"""Exercise ZLUDA's CUDA Driver and cuFFT APIs using synthetic input."""

import argparse
import ctypes as c
import math
import sys
from contextlib import ExitStack
from pathlib import Path

UINT = c.c_uint
INT = c.c_int
PTR = c.c_void_p
SIZE = c.c_size_t
DEVICE_PTR = c.c_uint64


def checked(dll, name, *types):
    function = getattr(dll, name)
    function.argtypes = types
    function.restype = INT

    def call(*args):
        result = function(*args)
        if result != 0:
            raise RuntimeError(f"{name} returned {result}")

    return call


def cuda_context(driver, cleanup, expected_device):
    checked(driver, "cuInit", UINT)(0)
    count = INT()
    checked(driver, "cuDeviceGetCount", c.POINTER(INT))(c.byref(count))
    name = c.create_string_buffer(256)
    get_name = checked(driver, "cuDeviceGetName", PTR, INT, INT)
    get_device = checked(driver, "cuDeviceGet", c.POINTER(INT), INT)
    for ordinal in range(count.value):
        device = INT()
        get_device(c.byref(device), ordinal)
        get_name(name, len(name), device)
        if expected_device.casefold() in name.value.decode().casefold():
            break
    else:
        raise RuntimeError(f"{expected_device} absent among {count.value} CUDA devices")
    print(f"CUDA device {ordinal}: {name.value.decode()}", flush=True)

    context = PTR()
    checked(driver, "cuDevicePrimaryCtxRetain", c.POINTER(PTR), INT)(c.byref(context), device)
    cleanup.callback(checked(driver, "cuDevicePrimaryCtxRelease_v2", INT), device)
    set_current = checked(driver, "cuCtxSetCurrent", PTR)
    set_current(context)
    cleanup.callback(set_current, None)


def allocate(driver, cleanup, size):
    address = DEVICE_PTR()
    checked(driver, "cuMemAlloc_v2", c.POINTER(DEVICE_PTR), SIZE)(c.byref(address), size)
    cleanup.callback(checked(driver, "cuMemFree_v2", DEVICE_PTR), address)
    return address


def test_ptx(driver):
    with ExitStack() as cleanup:
        module = PTR()
        ptx = Path(__file__).with_name("vector_transform.ptx").read_bytes()
        checked(driver, "cuModuleLoadData", c.POINTER(PTR), c.c_char_p)(c.byref(module), ptx)
        cleanup.callback(checked(driver, "cuModuleUnload", PTR), module)
        kernel = PTR()
        checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)(
            c.byref(kernel), module, b"vector_transform"
        )

        count, block_size = 257, 64
        input_data = (UINT * count)(*(index * 11 + 7 for index in range(count)))
        output_data = (UINT * count)()
        size = c.sizeof(input_data)
        source = allocate(driver, cleanup, size)
        destination = allocate(driver, cleanup, size)
        checked(driver, "cuMemcpyHtoD_v2", DEVICE_PTR, PTR, SIZE)(source, input_data, size)
        length = UINT(count)
        args = (PTR * 3)(c.addressof(source), c.addressof(destination), c.addressof(length))
        checked(driver, "cuLaunchKernel", PTR, *(UINT,) * 7, PTR, c.POINTER(PTR), PTR)(
            kernel, math.ceil(count / block_size), 1, 1, block_size, 1, 1, 0, None, args, None
        )
        checked(driver, "cuCtxSynchronize")()
        checked(driver, "cuMemcpyDtoH_v2", PTR, DEVICE_PTR, SIZE)(output_data, destination, size)
        for index, actual in enumerate(output_data):
            expected = 3 * input_data[index] + index
            if actual != expected:
                raise RuntimeError(f"PTX index {index}: got {actual}, expected {expected}")
    print(f"PASS: PTX kernel matched all {count} results", flush=True)


def test_fft(driver, fft):
    rows, columns = 4, 8
    inputs = (c.c_float * (2 * rows * columns))()
    # One complex impulse away from the origin produces known phases across the output.
    impulse_row, impulse_column = 1, 3
    offset = 2 * (impulse_row * columns + impulse_column)
    inputs[offset], inputs[offset + 1] = 1.25, -0.5
    output = type(inputs)()
    size = c.sizeof(inputs)
    with ExitStack() as cleanup:
        source = allocate(driver, cleanup, size)
        destination = allocate(driver, cleanup, size)
        checked(driver, "cuMemcpyHtoD_v2", DEVICE_PTR, PTR, SIZE)(source, inputs, size)
        plan = INT()
        checked(fft, "cufftPlan2d", c.POINTER(INT), INT, INT, INT)(
            c.byref(plan), rows, columns, 0x29  # CUFFT_C2C
        )
        cleanup.callback(checked(fft, "cufftDestroy", INT), plan)
        checked(fft, "cufftExecC2C", INT, DEVICE_PTR, DEVICE_PTR, INT)(
            plan, source, destination, -1  # CUFFT_FORWARD
        )
        checked(driver, "cuCtxSynchronize")()
        checked(driver, "cuMemcpyDtoH_v2", PTR, DEVICE_PTR, SIZE)(output, destination, size)

    for row in range(rows):
        for column in range(columns):
            phase = -math.tau * (row * impulse_row / rows + column * impulse_column / columns)
            expected = (1.25 - 0.5j) * complex(math.cos(phase), math.sin(phase))
            index = 2 * (row * columns + column)
            actual = complex(output[index], output[index + 1])
            if not abs(actual - expected) <= 1e-5:
                raise RuntimeError(f"FFT ({row}, {column}): got {actual}, expected {expected}")
    print(f"PASS: cuFFT 11 matched all {rows * columns} complex values", flush=True)


def test_atomic_reduction(driver, ptx_path):
    blocks, threads = 8, 64
    expected = blocks * threads * (threads + 1) // 2
    with ExitStack() as cleanup:
        module = PTR()
        checked(driver, "cuModuleLoadData", c.POINTER(PTR), c.c_char_p)(
            c.byref(module), ptx_path.read_bytes()
        )
        cleanup.callback(checked(driver, "cuModuleUnload", PTR), module)
        kernel = PTR()
        checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)(
            c.byref(kernel), module, b"atomic_reduction"
        )
        result = UINT()
        size = c.sizeof(result)
        output = allocate(driver, cleanup, size)
        checked(driver, "cuMemcpyHtoD_v2", DEVICE_PTR, PTR, SIZE)(output, c.byref(result), size)
        args = (PTR * 1)(c.addressof(output))
        checked(driver, "cuLaunchKernel", PTR, *(UINT,) * 7, PTR, c.POINTER(PTR), PTR)(
            kernel, blocks, 1, 1, threads, 1, 1, 0, None, args, None
        )
        checked(driver, "cuCtxSynchronize")()
        checked(driver, "cuMemcpyDtoH_v2", PTR, DEVICE_PTR, SIZE)(c.byref(result), output, size)
        if result.value != expected:
            raise RuntimeError(f"Atomic reduction: got {result.value}, expected {expected}")
    print(f"PASS: shared and global atomic reduction returned {expected}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zluda_dir", type=Path)
    parser.add_argument("--fft-dir", type=Path, help="Use cuFFT from a different ZLUDA directory")
    parser.add_argument("--device", default="Radeon RX 7900 XT")
    parser.add_argument("--atomic-reduction", type=Path, help="Run the atomic reduction test PTX")
    args = parser.parse_args()
    if sys.platform != "win32" or c.sizeof(PTR) != 8:
        parser.error("64-bit Python on Windows is required")

    directory = args.zluda_dir.resolve(strict=True)
    fft_directory = args.fft_dir.resolve(strict=True) if args.fft_dir else directory
    driver = c.WinDLL(str(directory / "nvcuda.dll"))
    with ExitStack() as cleanup:
        cuda_context(driver, cleanup, args.device)
        test_ptx(driver)
        test_fft(driver, c.WinDLL(str(fft_directory / "cufft64_11.dll")))
        if args.atomic_reduction:
            test_atomic_reduction(driver, args.atomic_reduction)


if __name__ == "__main__":
    try:
        main()
    except (OSError, AttributeError, RuntimeError) as error:
        sys.exit(f"FAIL: {error}")
