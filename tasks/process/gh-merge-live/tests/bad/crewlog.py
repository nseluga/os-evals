"""crewlog: append shift entries to a log file."""


def log_shift(path, crew, hours):
    with open(path, "a") as f:
        f.write(f"{crew}\t{hours}\n")
