"""
Scenario.py
===========
The sediment scenario of a run: one sediment delivery ratio (SDR) and one trapping efficiency
(TE), chosen in the terminal or with command-line options. Identical in the HydroSHEDS and
TDX-Hydro versions of the tool.

  SDR  Low   Diodato & Grauso (2009)  0.41 x A^-0.085
       High  Gourfi et al. (2018)     0.93 x A^-0.084
       User  a x A^b, with A the catchment area in km2 and a, b typed by the user
  TE   Low   Gill (1979) fit to the lower Brune curve (fine sediment)
       Medium  Brune median curve  (C/I) / (0.012 + 1.02 C/I)
       High  Gill (1979) fit to the upper Brune curve (coarse sediment)

Each run gives one CSV, named <portfolio>..._Scen<#>_SDR_<Low|High|User>_TE_<Low|Medium|High>,
where <#> is the next free scenario number of that portfolio. The a and b of a user-defined SDR
are not in the file name: they are in the diagnostics file and the figure footnote.

Imported by RunScreening.py.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

SDR_OPTIONS = {
    "Low": ("Diodato & Grauso (2009)", 0.41, -0.085),
    "High": ("Gourfi et al. (2018)", 0.93, -0.084),
    "User": ("user-defined", None, None),
}
TE_OPTIONS = {
    "Low": "Gill (1979) lower Brune curve, fine sediment",
    "Medium": "Brune median curve",
    "High": "Gill (1979) upper Brune curve, coarse sediment",
}
DEFAULT_SDR, DEFAULT_TE = "Low", "Low"


@dataclass(frozen=True)
class Scenario:
    sdr: str      # Low | High | User
    a: float
    b: float
    te: str       # Low | Medium | High

    @property
    def label(self):
        return f"SDR_{self.sdr}_TE_{self.te}"

    @property
    def description(self):
        source = SDR_OPTIONS[self.sdr][0]
        return f"SDR {self.sdr} ({source}): {self.a:g} × A^{self.b:g}  |  TE {self.te} ({TE_OPTIONS[self.te]})"


def add_arguments(ap):
    cap = str.capitalize
    ap.add_argument("--sdr", type=cap, choices=list(SDR_OPTIONS),
                    help="sediment delivery ratio: low (Diodato), high (Gourfi) or user (needs --a and --b)")
    ap.add_argument("--a", type=float, help="coefficient a of a user-defined SDR = a x A^b (A in km2)")
    ap.add_argument("--b", type=float, help="exponent b of a user-defined SDR = a x A^b")
    ap.add_argument("--te", type=cap, choices=list(TE_OPTIONS),
                    help="trapping efficiency: low (Gill, fine sediment), medium (Brune median) or high (Gill, coarse)")
    ap.add_argument("--scen-number", type=int, dest="scen_number",
                    help="scenario number <#> for the file names (default: next free one)")


def _ask_choice(title, options, default):
    keys = list(options)
    print(title)
    for i, k in enumerate(keys, 1):
        print(f"  {i}. {k:<7} {options[k]}")
    while True:
        raw = input(f"Choose [1-{len(keys)}, Enter = {default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            return keys[int(raw) - 1]
        print(f"  Please enter a number from 1 to {len(keys)}.")


def _ask_float(prompt, positive=False):
    while True:
        try:
            v = float(input(prompt).strip())
            if not positive or v > 0:
                return v
        except ValueError:
            pass
        print("  Please enter a " + ("positive " if positive else "") + "number.")


def from_args(args):
    """Resolve the scenario from the command line, asking in the terminal for what is missing
    (when run non-interactively the defaults Low / Low are used)."""
    interactive = sys.stdin.isatty()
    sdr = args.sdr or ("User" if (args.a is not None or args.b is not None) else None)
    if sdr is None:
        sdr = (_ask_choice("Sediment delivery ratio (SDR):",
                           {"Low": "Diodato & Grauso (2009): 0.41 x A^-0.085",
                            "High": "Gourfi et al. (2018): 0.93 x A^-0.084",
                            "User": "user-defined: a x A^b (A in km2)"}, DEFAULT_SDR)
               if interactive else DEFAULT_SDR)
    if sdr == "User":
        a = args.a if args.a is not None else (_ask_float("  a (> 0): ", positive=True) if interactive else None)
        b = args.b if args.b is not None else (_ask_float("  b (usually negative): ") if interactive else None)
        if a is None or b is None:
            raise SystemExit("A user-defined SDR needs both --a and --b.")
        if a <= 0:
            raise SystemExit("--a must be positive.")
        if b > 0:
            print("  ! b > 0: the delivery ratio would grow with catchment area; check the value.")
    else:
        if args.a is not None or args.b is not None:
            raise SystemExit("--a and --b only apply with --sdr user.")
        _, a, b = SDR_OPTIONS[sdr]
    te = args.te or (_ask_choice("Trapping efficiency (TE):", TE_OPTIONS, DEFAULT_TE) if interactive else DEFAULT_TE)
    return Scenario(sdr, a, b, te)


def next_number(folder, prefix):
    """Next unused scenario number among the <prefix>_Scen<#>_SDR_... files of a folder."""
    pat = re.compile(rf"^{re.escape(prefix)}_Scen(\d+)_SDR_")
    used = [int(m.group(1)) for p in Path(folder).glob("*.csv") if (m := pat.match(p.name))]
    return max(used, default=0) + 1
