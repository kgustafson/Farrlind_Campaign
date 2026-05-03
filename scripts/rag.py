import sys

from raglib.extract import extract_session
from raglib.filter_events impoirt filter_session
from raglib.merge import merge_session
from raglib_summarize import summarize_session
from raglib.validate import validate_session
from raglib_pipeline import run_pipeline

def main():
    if len(sys.argv) < 3:
        print("Usage: rag <command> <session>")
        print("       rag extract   <session>")
        print("       rag filter    <session>")
        print("       rag merge     <session>")
        print("       rag summarize <session>")
        print("       rag validate  <session>")
        print("       rag run       <session>")
        sys.exit(1)
    cmd = sys.argv[1]
    session = sys.argv[2]
    if cmd == "extract":
        extract_session(session)
    elif cmd == "filter":
        filter_session(session)
    elif cmd == "merge":
        merge_session(session)
    elif cmd == "summarize":
        summarize_session(session)
    elif cmd == "validate":
        validate_session(session)
    elif cmd == "run":
        run_pipeline(session)
    else: 
        print(f"Unknown command : {cmd}")

if __name__ == "__main__":
    main()
