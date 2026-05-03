import sys
from raglib.extract import extract_session
from raglib.filter_events import filter_session
from raglib.normalize import normalize_session
from raglib.merge import merge_session
from raglib.validate import validate_session
from raglib.summarize import summarize_session


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  rag extract session_name")
        print("  rag filter session_name")
        print("  rag normalize session_name")
        print("  rag merge session_name")
        print("  rag validate session_name")
        print("  rag summarize session_name")
        sys.exit(1)

    command = sys.argv[1]
    session_name = sys.argv[2]

    if command == "extract":
        extract_session(session_name)

    elif command == "filter":
        filter_session(session_name)

    elif command == "normalize":
        normalize_session(session_name)

    elif command == "merge":
        merge_session(session_name)

    elif command == "validate":
        validate_session(session_name)

    elif command == "summarize":
        summarize_session(session_name)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
