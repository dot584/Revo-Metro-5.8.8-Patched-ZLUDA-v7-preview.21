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

CU_STREAM_DEFAULT = 0x0
CU_STREAM_NON_BLOCKING = 0x1
CU_STREAM_LEGACY = PTR(0x1)
CU_STREAM_PER_THREAD = PTR(0x2)
CUDA_ERROR_NOT_READY = 600

STREAM_SYNC_PTX = b"""\
.version 7.0
.target sm_70
.address_size 64

.visible .entry delay_and_write(
    .param .u64 out_ptr,
    .param .u32 loops,
    .param .u32 val
)
{
    .reg .pred %p1;
    .reg .b32 %r<4>;
    .reg .b64 %rd<3>;

    ld.param.u64 %rd1, [out_ptr];
    ld.param.u32 %r1, [loops];
    ld.param.u32 %r2, [val];
    mov.u32 %r3, 0;

L_loop:
    setp.ge.u32 %p1, %r3, %r1;
    @%p1 bra L_done;
    add.u32 %r3, %r3, 1;
    bra L_loop;

L_done:
    cvta.to.global.u64 %rd2, %rd1;
    st.global.wt.u32 [%rd2], %r2;
    ret;
}

.visible .entry read_and_add(
    .param .u64 in_ptr,
    .param .u64 out_ptr,
    .param .u32 addend
)
{
    .reg .b32 %r<4>;
    .reg .b64 %rd<5>;

    ld.param.u64 %rd1, [in_ptr];
    ld.param.u64 %rd2, [out_ptr];
    ld.param.u32 %r1, [addend];
    cvta.to.global.u64 %rd3, %rd1;
    cvta.to.global.u64 %rd4, %rd2;
    ld.global.cv.u32 %r2, [%rd3];
    add.u32 %r3, %r2, %r1;
    st.global.wt.u32 [%rd4], %r3;
    ret;
}
\0"""


class CUlaunchConfig(c.Structure):
    _fields_ = [
        ("gridDimX", UINT),
        ("gridDimY", UINT),
        ("gridDimZ", UINT),
        ("blockDimX", UINT),
        ("blockDimY", UINT),
        ("blockDimZ", UINT),
        ("sharedMemBytes", UINT),
        ("hStream", PTR),
        ("attrs", PTR),
        ("numAttrs", UINT),
    ]


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


def test_streams(driver):
    with ExitStack() as cleanup:
        module = PTR()
        ptx = Path(__file__).with_name("vector_transform.ptx").read_bytes()
        checked(driver, "cuModuleLoadData", c.POINTER(PTR), c.c_char_p)(c.byref(module), ptx)
        cleanup.callback(checked(driver, "cuModuleUnload", PTR), module)
        kernel = PTR()
        checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)(
            c.byref(kernel), module, b"vector_transform"
        )

        sync_module = PTR()
        checked(driver, "cuModuleLoadData", c.POINTER(PTR), c.c_char_p)(
            c.byref(sync_module), STREAM_SYNC_PTX
        )
        cleanup.callback(checked(driver, "cuModuleUnload", PTR), sync_module)
        delay_kernel, read_kernel = PTR(), PTR()
        checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)(
            c.byref(delay_kernel), sync_module, b"delay_and_write"
        )
        checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)(
            c.byref(read_kernel), sync_module, b"read_and_add"
        )

        create_stream = checked(driver, "cuStreamCreate", c.POINTER(PTR), UINT)
        destroy_stream = checked(driver, "cuStreamDestroy_v2", PTR)
        blocking_stream = PTR()
        create_stream(c.byref(blocking_stream), CU_STREAM_DEFAULT)
        cleanup.callback(destroy_stream, blocking_stream)
        non_blocking_stream = PTR()
        create_stream(c.byref(non_blocking_stream), CU_STREAM_NON_BLOCKING)
        cleanup.callback(destroy_stream, non_blocking_stream)

        event = PTR()
        checked(driver, "cuEventCreate", c.POINTER(PTR), UINT)(c.byref(event), 0)
        cleanup.callback(checked(driver, "cuEventDestroy_v2", PTR), event)

        count, block_size = 257, 64
        grid_x = math.ceil(count / block_size)
        output_data = (UINT * count)()
        size = c.sizeof(output_data)
        source = allocate(driver, cleanup, size)
        destination = allocate(driver, cleanup, size)
        length = UINT(count)
        args = (PTR * 3)(c.addressof(source), c.addressof(destination), c.addressof(length))

        memset_async = checked(driver, "cuMemsetD32Async", DEVICE_PTR, UINT, SIZE, PTR)
        htod_async = checked(driver, "cuMemcpyHtoDAsync_v2", DEVICE_PTR, PTR, SIZE, PTR)
        dtoh_async = checked(driver, "cuMemcpyDtoHAsync_v2", PTR, DEVICE_PTR, SIZE, PTR)
        launch = checked(driver, "cuLaunchKernel", PTR, *(UINT,) * 7, PTR, c.POINTER(PTR), PTR)
        launch_ex = checked(
            driver, "cuLaunchKernelEx", c.POINTER(CUlaunchConfig), PTR, c.POINTER(PTR), PTR
        )
        record_event = checked(driver, "cuEventRecord", PTR, PTR)
        wait_event = checked(driver, "cuStreamWaitEvent", PTR, PTR, UINT)
        sync_stream = checked(driver, "cuStreamSynchronize", PTR)
        query_stream = getattr(driver, "cuStreamQuery")
        query_stream.argtypes = (PTR,)
        query_stream.restype = INT

        stream_cases = (
            ("null/default", None),
            ("explicit legacy (0x1)", CU_STREAM_LEGACY),
            ("per-thread default (0x2)", CU_STREAM_PER_THREAD),
            ("ordinary blocking", blocking_stream),
            ("ordinary non-blocking", non_blocking_stream),
        )
        for case_index, (label, stream) in enumerate(stream_cases, start=1):
            seed = case_index * 17
            input_data = (UINT * count)(*(index * 11 + seed for index in range(count)))
            memset_async(destination, 0, count, stream)
            htod_async(source, input_data, size, stream)
            launch(kernel, grid_x, 1, 1, block_size, 1, 1, 0, stream, args, None)
            record_event(event, stream)
            wait_event(stream, event, 0)
            dtoh_async(output_data, destination, size, stream)
            sync_stream(stream)
            status = query_stream(stream)
            if status != 0:
                raise RuntimeError(f"cuStreamQuery({label}) returned {status}")
            for index, actual in enumerate(output_data):
                expected = 3 * input_data[index] + index
                if actual != expected:
                    raise RuntimeError(
                        f"Stream {label} index {index}: got {actual}, expected {expected}"
                    )

            ex_input = (UINT * count)(*(index * 13 + seed + 3 for index in range(count)))
            config = CUlaunchConfig(grid_x, 1, 1, block_size, 1, 1, 0, stream, None, 0)
            memset_async(destination, 0, count, stream)
            htod_async(source, ex_input, size, stream)
            launch_ex(c.byref(config), kernel, args, None)
            dtoh_async(output_data, destination, size, stream)
            sync_stream(stream)
            for index, actual in enumerate(output_data):
                expected = 3 * ex_input[index] + index
                if actual != expected:
                    raise RuntimeError(
                        f"cuLaunchKernelEx({label}) index {index}: got {actual}, expected {expected}"
                    )

        # Verify CUDA legacy default-stream synchronization semantics with blocking streams.
        d_stage = allocate(driver, cleanup, c.sizeof(UINT))
        d_final = allocate(driver, cleanup, c.sizeof(UINT))
        memset_d32 = checked(driver, "cuMemsetD32_v2", DEVICE_PTR, UINT, SIZE)
        dtoh = checked(driver, "cuMemcpyDtoH_v2", PTR, DEVICE_PTR, SIZE)
        loops = UINT(10_000_000)

        # 1. Work on a blocking stream must complete before subsequent CU_STREAM_LEGACY work starts.
        memset_d32(d_stage, 0, 1)
        memset_d32(d_final, 0, 1)
        written_value = UINT(42)
        addend = UINT(8)
        delay_args = (PTR * 3)(
            c.addressof(d_stage), c.addressof(loops), c.addressof(written_value)
        )
        read_args = (PTR * 3)(
            c.addressof(d_stage), c.addressof(d_final), c.addressof(addend)
        )
        launch(delay_kernel, 1, 1, 1, 1, 1, 1, 0, blocking_stream, delay_args, None)
        in_flight = query_stream(blocking_stream)
        if in_flight not in (0, CUDA_ERROR_NOT_READY):
            raise RuntimeError(f"cuStreamQuery(blocking) returned {in_flight}")
        launch(read_kernel, 1, 1, 1, 1, 1, 1, 0, CU_STREAM_LEGACY, read_args, None)
        sync_stream(CU_STREAM_LEGACY)
        after_legacy = query_stream(blocking_stream)
        if after_legacy != 0:
            raise RuntimeError(
                f"Blocking stream not synchronized by legacy launch: status {after_legacy}"
            )
        actual_sum = UINT()
        dtoh(c.byref(actual_sum), d_final, c.sizeof(actual_sum))
        if actual_sum.value != 50:
            raise RuntimeError(
                f"Blocking -> legacy sync failed: got {actual_sum.value}, expected 50"
            )

        # 2. Work on CU_STREAM_LEGACY must complete before subsequent blocking-stream work starts.
        memset_d32(d_stage, 0, 1)
        memset_d32(d_final, 0, 1)
        written_value.value = 73
        addend.value = 19
        launch(delay_kernel, 1, 1, 1, 1, 1, 1, 0, CU_STREAM_LEGACY, delay_args, None)
        in_flight = query_stream(CU_STREAM_LEGACY)
        if in_flight not in (0, CUDA_ERROR_NOT_READY):
            raise RuntimeError(f"cuStreamQuery(CU_STREAM_LEGACY) returned {in_flight}")
        launch(read_kernel, 1, 1, 1, 1, 1, 1, 0, blocking_stream, read_args, None)
        sync_stream(blocking_stream)
        after_blocking = query_stream(CU_STREAM_LEGACY)
        if after_blocking != 0:
            raise RuntimeError(
                f"Legacy stream not synchronized by blocking launch: status {after_blocking}"
            )
        dtoh(c.byref(actual_sum), d_final, c.sizeof(actual_sum))
        if actual_sum.value != 92:
            raise RuntimeError(
                f"Legacy -> blocking sync failed: got {actual_sum.value}, expected 92"
            )

        # 3. cuStreamSynchronize(CU_STREAM_LEGACY) must wait on prior blocking-stream work.
        memset_d32(d_stage, 0, 1)
        written_value.value = 105
        launch(delay_kernel, 1, 1, 1, 1, 1, 1, 0, blocking_stream, delay_args, None)
        sync_stream(CU_STREAM_LEGACY)
        if query_stream(blocking_stream) != 0:
            raise RuntimeError("cuStreamSynchronize(CU_STREAM_LEGACY) did not drain blocking stream")
        dtoh(c.byref(actual_sum), d_stage, c.sizeof(actual_sum))
        if actual_sum.value != 105:
            raise RuntimeError(
                f"cuStreamSynchronize(CU_STREAM_LEGACY) value mismatch: got {actual_sum.value}, expected 105"
            )

    print(
        "PASS: null, explicit legacy (0x1), per-thread (0x2), blocking, and non-blocking streams verified with legacy synchronization",
        flush=True,
    )


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
        test_streams(driver)
        test_fft(driver, c.WinDLL(str(fft_directory / "cufft64_11.dll")))
        if args.atomic_reduction:
            test_atomic_reduction(driver, args.atomic_reduction)


if __name__ == "__main__":
    try:
        main()
    except (OSError, AttributeError, RuntimeError) as error:
        sys.exit(f"FAIL: {error}")
