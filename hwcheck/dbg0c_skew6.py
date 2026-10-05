"""Milestone 0c investigation, part 6: which part of connect() makes the
CH2-CH1 offset slip by +2 ns, and how often.

Part 5: the offset slipped +2000 ps at 2 of 9 full connect() calls and at none
of 12 CH3 toggles, 3 CH2 toggles, 3 ':RUN', 3 device clears, 3 WAVeform
MODE+FORMat writes. Slips accumulate (+150 -> +2150 -> +4150 ps).

connect() = session close/open, then resync(): ':RUN', wait 0.3 s, device clear
(close, pyusb set_configuration + INITIATE_CLEAR + clear_halt, reopen),
sentinel burst (*IDN? / *OPC? / *IDN? x3), then WAVeform MODE + FORMat.

Usage: python dbg0c_skew6.py <variant> [reps]
  full        the whole connect()
  run_clear   ':RUN', 0.3 s, device clear
  clear       device clear only
  clear_burst device clear, then the sentinel burst at once
  run         ':RUN' only
  setconf     pyusb set_configuration only (no INITIATE_CLEAR, no clear_halt)
  initclear   INITIATE_CLEAR + CHECK_CLEAR_STATUS only (no set_configuration, no clear_halt)
  halt        clear_halt on both endpoints only
Each repetition: do the action, then 2 single-shot two-channel captures at
20 MHz; a change of more than 500 ps from the previous value counts as a slip.
Same wiring (both 10X probes on generator CH1) and safety rules."""

def _run_guard():
    """This script deliberately sends ':RUN' to the scope. Since Milestone 0c that
    is known to shift the scope's channels against each other (HW_REPORT.md 12.11),
    so it refuses to start unless that is explicitly accepted."""
    import sys
    if "--allow-run" not in sys.argv:
        raise SystemExit(__file__ + ": historical script that sends ':RUN' (shifts the scope's channel "
                         "alignment). Not run. Pass --allow-run to run it anyway, then use s0c_realign.py.")
    sys.argv.remove("--allow-run")


_run_guard()
import sys
import time
import traceback

import libusb_package
import usb.util

import iolayer as io
import dbg0c_skew
from common import GEN_PID, GEN_VID, SCOPE_PID, SCOPE_VID, find_resource, open_rm, save
from dbg0c_skew import F, TB_STEPS, VD_STEPS, measure, out
from usbclear import usbtmc_clear

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "full"
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 25
dbg0c_skew.N = 2


def usb_part(what):
    dev = libusb_package.find(idVendor=SCOPE_VID, idProduct=SCOPE_PID)
    try:
        if what == "setconf":
            dev.set_configuration()
            return
        intf = dev.get_active_configuration()[(0, 0)]
        usb.util.claim_interface(dev, intf.bInterfaceNumber)
        try:
            if what == "initclear":
                bm = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS,
                                                 usb.util.CTRL_RECIPIENT_INTERFACE)
                dev.ctrl_transfer(bm, 5, 0, intf.bInterfaceNumber, 1, timeout=2000)
                for _ in range(20):
                    r = dev.ctrl_transfer(bm, 6, 0, intf.bInterfaceNumber, 2, timeout=2000)
                    if r[0] != 2:
                        break
                    time.sleep(0.1)
            elif what == "halt":
                for ep in intf:
                    dev.clear_halt(ep.bEndpointAddress)
        finally:
            usb.util.release_interface(dev, intf.bInterfaceNumber)
    finally:
        usb.util.dispose_resources(dev)


def main():
    rm = open_rm("@py")
    g = io.GenIO(rm, find_resource(rm, GEN_VID, GEN_PID))
    res = find_resource(rm, SCOPE_VID, SCOPE_PID)
    H = {"sc": io.ScopeIO(rm, res)}
    try:
        sc = H["sc"]
        g.connect()
        sc.idn = sc.query("*IDN?", io.v_scope_idn)
        g.output(1, False)
        g.output(2, False)
        # settings are left as the previous investigation scripts set them, then restored by
        # those scripts; set what this test needs and verify (no Saver: nothing new is changed
        # beyond what dbg0c_skew5 already saved/restored, and the end of this script puts back
        # the values read here)
        tb0 = sc.query(":TIMebase:SCALe?", io.v_float)
        v0 = [sc.query(f":CHANnel{ch}:SCALe?", io.v_float) for ch in (1, 2)]
        out["found"] = dict(tb=tb0, vdiv=v0)
        g_freq0 = g.query(":CHANnel1:BASE:FREQuency?", io.v_float)
        g_unit0 = g.query(":CHANnel1:AMPLitude:UNIT?", g.V_UNIT)
        g_amp0 = g.query(":CHANnel1:BASE:AMPLitude?", io.v_float)
        g.configure_sine(1, F, 1.0, 0.0, "HIGHZ")
        for ch in (1, 2):
            sc.configure_channel(ch, "DC", False, 0.0)
        sc.tb_steps, sc.vdiv_steps = TB_STEPS, VD_STEPS
        for ch in (1, 2):
            sc.set_vdiv(ch, 0.02, "exact")
        sc.set_trigger_edge(1, 0.0, "POSitive", "AUTO")
        sc.set_timebase(25e-9, "exact")
        g.output(1, True)
        time.sleep(2.0)

        S = lambda: H["sc"]

        def carry(new, old):
            new.tb, new.tb_steps, new.vdiv_steps, new.vdiv = old.tb, old.tb_steps, old.vdiv_steps, dict(old.vdiv)
            H["sc"] = new

        def with_closed(fn):
            old = S()
            old.close()
            time.sleep(0.3)
            fn()
            time.sleep(0.3)
            n = io.ScopeIO(rm, res)
            carry(n, old)

        def burst():
            s = S()
            for _ in range(3):
                s._ask_text("*IDN?"); s._ask_text("*OPC?"); s._ask_text("*IDN?")

        def full():
            old = S()
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            n.connect(build_tables=False)
            carry(n, old)
            n.tb = 25e-9

        def wav():
            S().set_verified(":WAVeform:MODE", "NORMal", io.V_WAVMODE, "NORMal")
            S().set_verified(":WAVeform:FORMat", "BYTE", io.V_WAVFMT, "BYTE")

        def instclear():
            try:
                S().inst.clear()
            except Exception:
                pass

        def resync_only():
            S().resync(run_wait=0.3)

        def reopen_resync():            # connect() without the WAVeform writes
            old = S()
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            carry(n, old)
            n.resync(run_wait=0.3)

        def reopen_wav():               # connect() without resync
            old = S()
            old.close()
            time.sleep(0.5)
            n = io.ScopeIO(rm, res)
            carry(n, old)
            wav()

        def reopen_then(fn, wait=0.0):
            def f():
                old = S()
                old.close()
                time.sleep(0.5)
                n = io.ScopeIO(rm, res)
                carry(n, old)
                if wait:
                    time.sleep(wait)
                fn()
            return f

        def clear_now():
            with_closed(lambda: usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False))

        def idn_then_run():
            S().query("*IDN?", io.v_scope_idn)
            S().query(":TIMebase:SCALe?", io.v_float)
            S().inst.write(":RUN")

        def auto_only():
            S().set_verified(":TRIGger:SWEep", "AUTO", io.V_SWEEP, "AUTO")
            time.sleep(0.8)
            out.setdefault("status_after_auto_only", []).append(S().status())

        acts = {
            # fourth round (third: reopen_run 8/25, reopen_clear 0/25, reopen_wait_resync 13/25,
            # reopen_sentinel 0/25)
            "reopen_idn_run": reopen_then(idn_then_run),
            "reopen_auto": reopen_then(auto_only),
            "run_raw": lambda: S().inst.write(":RUN"),
            "free_run": lambda: S().free_run(),
            "auto_only": auto_only,
            # third round (second round: wav 0/25, resync 0/25, reopen_wav 0/25, reopen_resync 15/25)
            "reopen_wait_resync": reopen_then(lambda: S().resync(run_wait=0.3), wait=3.0),
            "reopen_run": reopen_then(lambda: S().inst.write(":RUN")),
            "reopen_clear": reopen_then(clear_now),
            "reopen_instclear": reopen_then(instclear),
            "reopen_sentinel": reopen_then(lambda: S().query("*IDN?", io.v_scope_idn)),
            # second round of variants (first round: full 11/25, run_clear 1/25, clear 0/25)
            "resync": resync_only,
            "wav": wav,
            "wavmode": lambda: S().set_verified(":WAVeform:MODE", "NORMal", io.V_WAVMODE, "NORMal"),
            "wavfmt": lambda: S().set_verified(":WAVeform:FORMat", "BYTE", io.V_WAVFMT, "BYTE"),
            "instclear": instclear,
            "reopen_resync": reopen_resync,
            "reopen_wav": reopen_wav,
            "burst": burst,
            "full": full,
            "run_clear": lambda: (S().inst.write(":RUN"), time.sleep(0.3),
                                  with_closed(lambda: usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False))),
            "clear": lambda: with_closed(lambda: usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False)),
            "clear_burst": lambda: (with_closed(lambda: usbtmc_clear(SCOPE_VID, SCOPE_PID, verbose=False)), burst()),
            "run": lambda: S().write(":RUN"),
            "setconf": lambda: with_closed(lambda: usb_part("setconf")),
            "initclear": lambda: with_closed(lambda: usb_part("initclear")),
            "halt": lambda: with_closed(lambda: usb_part("halt")),
        }
        act = acts[VARIANT]
        last = measure(S(), f"[{VARIANT}] start")
        slips = []
        for i in range(1, REPS + 1):
            try:
                act()
                time.sleep(0.5)
                r = measure(S(), f"[{VARIANT}] #{i}")
                jump = r["delay_ps"] - last["delay_ps"]
                slips.append(round(jump / 1000.0) * 1000 if abs(jump) > 500 else 0)
                if slips[-1]:
                    print(f"      ^^^ SLIP {jump:+.0f} ps")
                last = r
            except Exception as e:
                print(f"#{i}: ERROR {type(e).__name__}: {str(e)[:300]}")
                slips.append("error")
        n = sum(1 for s in slips if s not in (0, "error"))
        out["variant"], out["slips"] = VARIANT, slips
        print(f"\nRESULT [{VARIANT}]: {n} slips in {len(slips)} repetitions: {slips}")
        if "status_after_auto_only" in out:
            print("   status 0.8 s after sweep AUTO without :RUN:", sorted(set(out["status_after_auto_only"])))
        # put back what was read at the start
        sc = S()
        sc.set_timebase(tb0, "exact") if any(abs(tb0 - s) < 1e-3 * s for s in TB_STEPS) else None
        for ch, v in zip((1, 2), v0):
            sc.set_verified(f":CHANnel{ch}:SCALe", io.plain_decimal(v), io.v_float, v)
        g.safe_off()
        g.set_verified(":CHANnel1:BASE:FREQuency", io.GenFmt.num(g_freq0), io.v_float, g_freq0)
        g.set_verified(":CHANnel1:AMPLitude:UNIT", g_unit0, g.V_UNIT, g_unit0)
        g.set_verified(":CHANnel1:BASE:AMPLitude", io.GenFmt.num(g_amp0), io.v_float, g_amp0)
    except Exception:
        out["fatal"] = traceback.format_exc()
        print(out["fatal"])
    finally:
        g.safe_off()
        try:
            print("generator outputs ON at end?", [g.output(1), g.output(2)])
        except Exception as e:
            print("gen end error", e)
        g.close()
        H["sc"].close()
        rm.close()
        print("saved", save(f"dbg0c_skew6_{VARIANT}.json", out))


if __name__ == "__main__":
    main()
