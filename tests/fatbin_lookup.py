"""Check kernel lookup across two independently compiled PTX fatbin members."""

import argparse
import ctypes as c
import struct
from contextlib import ExitStack
from pathlib import Path

from gpu_smoke import DEVICE_PTR, INT, PTR, SIZE, UINT, allocate, checked, cuda_context


def fatbin(body):
    ptx = (".version 8.4\n.target sm_86\n.address_size 64\n" + body).encode("ascii")
    ptx += bytes(8 - len(ptx) % 8)
    file_header = struct.pack(
        "<HHIIIIIIIIIQQQ", 1, 0x101, 64, len(ptx), 0, 0, 0, 0, 86, 64, 0, 1, 0, 0
    )
    header = struct.pack("<IHHQ", 0xBA55ED50, 1, 16, len(file_header) + len(ptx))
    return c.create_string_buffer(header + file_header + ptx)


class Wrapper(c.Structure):
    _fields_ = [("magic", UINT), ("version", UINT), ("data", PTR), ("submodules", PTR)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zluda_dir", type=Path)
    parser.add_argument("--lookup-only", action="store_true")
    args = parser.parse_args()
    driver = c.WinDLL(str((args.zluda_dir / "nvcuda.dll").resolve(strict=True)))

    names = ("fatbin_first", "fatbin_second")
    standalone = [fatbin(f".visible .entry {name}() {{ ret; }}") for name in names]
    members = standalone if args.lookup_only else [
        fatbin("""
            .visible .entry fatbin_first() { ret; }
            .weak .entry shared_template() { ret; }
            .visible .func store_result(.param .b64 ptr) {
                .reg .b64 %address;
                .reg .b32 %value;
                ld.param.u64 %address, [ptr];
                cvta.to.global.u64 %address, %address;
                mov.u32 %value, 79;
                st.global.u32 [%address], %value;
                ret;
            }
        """),
        fatbin("""
            .extern .func store_result(.param .b64 ptr);
            .weak .entry shared_template() { ret; }
            .visible .entry fatbin_second(.param .b64 ptr) {
                .reg .b64 %address;
                .param .b64 call_ptr;
                ld.param.u64 %address, [ptr];
                st.param.b64 [call_ptr], %address;
                call.uni store_result, (call_ptr);
                ret;
            }
        """),
    ]
    entries = (PTR * 3)(*(c.addressof(member) for member in members), None)
    wrapper = Wrapper(0x466243B1, 2, None, c.addressof(entries))
    with ExitStack() as cleanup:
        cuda_context(driver, cleanup, "Radeon RX 7900 XT")
        with ExitStack() as libraries:
            # A one-member control for each image proves that the encoding and
            # each individual kernel work before testing the wrapper.
            for name, member in zip(names, standalone, strict=True):
                module = PTR()
                checked(driver, "cuModuleLoadData", c.POINTER(PTR), PTR)(
                    c.byref(module), member
                )
                libraries.callback(checked(driver, "cuModuleUnload", PTR), module)
                checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)(
                    c.byref(PTR()), module, name.encode("ascii")
                )
                print(f"PASS: standalone image contains {name}", flush=True)

            library, module = PTR(), PTR()
            preserve_option = INT(1)  # CU_LIBRARY_BINARY_IS_PRESERVED
            checked(driver, "cuLibraryLoadData", c.POINTER(PTR), PTR, PTR, PTR, UINT, PTR, PTR, UINT)(
                c.byref(library), c.byref(wrapper), None, None, 0, c.byref(preserve_option), None, 1
            )
            libraries.callback(checked(driver, "cuLibraryUnload", PTR), library)
            checked(driver, "cuLibraryGetModule", c.POINTER(PTR), PTR)(c.byref(module), library)
            get_function = checked(driver, "cuModuleGetFunction", c.POINTER(PTR), PTR, c.c_char_p)
            missing = []
            functions = {}
            for name in names:
                try:
                    function = PTR()
                    get_function(c.byref(function), module, name.encode("ascii"))
                    functions[name] = function
                    print(f"PASS: multi-image wrapper contains {name}", flush=True)
                except RuntimeError as error:
                    missing.append(f"{name}: {error}")
            if missing:
                raise SystemExit("FAIL: " + ", ".join(missing))
            if args.lookup_only:
                return
            get_function(c.byref(PTR()), module, b"shared_template")
            print("PASS: repeated weak kernel resolved", flush=True)
            result = UINT()
            output = allocate(driver, libraries, c.sizeof(result))
            checked(driver, "cuMemcpyHtoD_v2", DEVICE_PTR, PTR, SIZE)(
                output, c.byref(result), c.sizeof(result)
            )
            params = (PTR * 1)(c.addressof(output))
            checked(driver, "cuLaunchKernel", PTR, *(UINT,) * 7, PTR, c.POINTER(PTR), PTR)(
                functions["fatbin_second"], 1, 1, 1, 1, 1, 1, 0, None, params, None
            )
            checked(driver, "cuCtxSynchronize")()
            checked(driver, "cuMemcpyDtoH_v2", PTR, DEVICE_PTR, SIZE)(
                c.byref(result), output, c.sizeof(result)
            )
            if result.value != 79:
                raise SystemExit(f"FAIL: cross-image device call returned {result.value}, expected 79")
            print("PASS: cross-image device call returned 79", flush=True)


if __name__ == "__main__":
    main()
