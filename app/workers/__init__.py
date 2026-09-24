"""Qt worker threads bridging the async engines to the GUI.

Each worker runs its own asyncio event loop in a background QThread and reports
progress/results via Qt signals, so the GUI thread never performs blocking
network or database work.
"""
