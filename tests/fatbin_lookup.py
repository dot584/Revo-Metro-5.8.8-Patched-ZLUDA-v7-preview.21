"""Check kernel lookup across two independently compiled PTX fatbin members."""

import argparse
import ctypes as c
import struct
from contextlib import ExitStack
from pathlib import Path

from gpu_smoke import INT, PTR, UINT, checked, cuda_context


def fatbin(kernel):
    ptx = (
        ".version 8.4\n.target sm_86\n.address_size 64\n"
        f".visible .entry {kernel}() {{ ret; }}\n"
    ).encode("ascii")
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
    args = parser.parse_args()
    driver = c.WinDLL(str((args.zluda_dir / "nvcuda.dll").resolve(strict=True)))

    names = ("fatbin_first", "fatbin_second")
    members = [fatbin(name) for name in names]
    entries = (PTR * 3)(*(c.addressof(member) for member in members), None)
    wrapper = Wrapper(0x466243B1, 2, None, c.addressof(entries))
    with ExitStack() as cleanup:
        cuda_context(driver, cleanup, "Radeon RX 7900 XT")
        with ExitStack() as libraries:
            # A one-member control for each image proves that the encoding and
            # each individual kernel work before testing the wrapper.
            for name, member in zip(names, members, strict=True):
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
            for name in names:
                try:
                    get_function(c.byref(PTR()), module, name.encode("ascii"))
                    print(f"PASS: multi-image wrapper contains {name}", flush=True)
                except RuntimeError as error:
                    missing.append(f"{name}: {error}")
            if missing:
                raise SystemExit("FAIL: " + ", ".join(missing))


if __name__ == "__main__":
    main()
