import uuid
from pathlib import Path

from langgraph.types import Command

from graph import graph


print("=" * 70)
print("ServiceNow ITOM AI Assistant - Interactive Test")
print("=" * 70)


# ---------------------------------------------------------
# Get user question
# ---------------------------------------------------------

question = input("\nEnter your question: ").strip()


# ---------------------------------------------------------
# Optional image input
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("OPTIONAL IMAGE EVIDENCE")
print("=" * 70)

print(
    "\nIf you have a screenshot, error message, log image, "
    "or other evidence, enter the full image path."
)

print("Press ENTER if you do not want to provide an image.")

image_path_input = input("\nImage path: ").strip().strip('"').strip("'")

image_path = None

if image_path_input:

    candidate = Path(image_path_input)

    if not candidate.exists():
        print("\nERROR: Image file does not exist.")
        print("Please check the path and run the test again.")
        raise SystemExit

    if not candidate.is_file():
        print("\nERROR: The provided path is not a file.")
        raise SystemExit

    allowed_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
    }

    if candidate.suffix.lower() not in allowed_extensions:
        print(
            "\nERROR: Unsupported image format."
            "\nSupported formats: PNG, JPG, JPEG, WEBP, GIF"
        )
        raise SystemExit

    image_path = str(candidate.resolve())

    print("\nImage accepted.")
    print("Image:", image_path)

else:

    print("\nNo image provided.")


# ---------------------------------------------------------
# Run LangGraph
# ---------------------------------------------------------
# IMPORTANT:
#
# graph.py owns the ENTIRE interactive workflow for
# incidents: satisfaction check, incident-creation
# confirmation, priority selection, validation, and
# incident creation all happen INSIDE the graph nodes
# (they call input()/print() themselves and are wired
# together with add_edge / add_conditional_edges).
#
# A single graph.invoke() call therefore walks all the
# way through to END, asking whatever questions are
# needed along the way.
#
# test_graph.py must NOT re-implement any of that
# workflow here - doing so is what caused every question
# (satisfaction / create-incident / priority) to be asked
# twice, once inside graph.invoke() and once again in this
# script afterwards.
# ---------------------------------------------------------

graph_input = {
    "question": question
}

if image_path:
    graph_input["image_path"] = image_path


# ---------------------------------------------------------
# The graph now pauses on interrupt() instead of blocking on
# input() internally, so we drive the resume loop here: every
# time invoke() comes back with "__interrupt__", show the
# question/options it's carrying, collect an answer, and
# resume the same thread with Command(resume=answer).
# ---------------------------------------------------------

thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}

result = graph.invoke(graph_input, config=config)

while "__interrupt__" in result:

    payload = result["__interrupt__"][0].value

    print("\n" + "=" * 70)
    print(payload.get("message", ""))

    options = payload.get("options")
    if options:
        for i, option in enumerate(options, start=1):
            print(f"{i}. {option}")

    answer = input("\n> ").strip()

    result = graph.invoke(Command(resume=answer), config=config)


# ---------------------------------------------------------
# Show image information (informational only)
# ---------------------------------------------------------

if image_path:

    print("\n" + "=" * 70)
    print("IMAGE EVIDENCE")
    print("=" * 70)

    print("Image received successfully.")
    print("Path:", image_path)

# ---------------------------------------------------------
# Display final result
# ---------------------------------------------------------
# By the time invoke() returns, the graph has already run
# through classification, troubleshooting, and (if the user
# chose to go that route) the full incident workflow. The
# final "response" already reflects the end state - a
# "no incident created" message, an incident-created
# confirmation, or a blocked-priority message - so we just
# print it once here.
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("ASSISTANT")
print("=" * 70)

print(result.get("response", ""))

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)