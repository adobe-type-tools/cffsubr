import sys
import afdko_tx


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    return afdko_tx.run(*args).returncode


if __name__ == "__main__":
    sys.exit(main())
