"""Allow running as: python -m minidsp"""
import sys

if "--gui" in sys.argv:
    sys.argv.remove("--gui")
    from .gui.app import run_gui
    run_gui()
else:
    from .cli import main
    main()
