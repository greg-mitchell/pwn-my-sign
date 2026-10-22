# Test Style

## Pytest style

- Extract fixtures for common setup
- Prefer fixtures over `@patch`, `with patch(...)`
- Use unittest.Mock (preferably with `spec=` set) to create a test double
- Use `monkeypatch` Pytest fixture to set env vars if needed
- Parameterize tests `@pytest.mark.parameterize` with exactly the same structure and assertions
- Only use classes to group test cases for large and complex test suites. A class should contain common setup
- Mark any tests that have slow computations with `@pytest.mark.slow`, and have external deps with `@pytest.mark.e2e`

## Behavioral testing

- Use a consistent arrange / act / assert block structure for tests
- Arrange should set up the input and state of the world *only as required* for the behavior under test
- General setup using safe (like no-op or empty) defaults should be extracted to fixtures
- Complex test data should be extracted to factories or fluent-style builders with defaults and optional overrides
- Act should call a public method on the unit under test using the arranged input
- Assert should be a single "fact". Split multiple separate facts about a behavior to separate cases to improve debug
  signal
- Typically each public method should have at least tests asserting how they call each dependency, and how they handle
  happy and error path cases from each call.
- Additionally, any combination of public methods that have shared state, ordering properties, or other joint behavior
  should be asserted.

## Test hierarchy

- Always define unit tests for happy and unhappy paths for each unit (typically the public members of a module)
- If several public classes are intended to work together, define integration tests for their combined units
- Unit tests *must not* use flaky or slow syscalls. I.e. no network, threading, subprocess.
- File access is acceptable using the pytest `tmpdir` fixture (which often is backed by a ramdisk)
- This project defines integration tests as fast, in-process tests like unit tests that pull together multiple units.
- If we use an external dependency (like a network call), these are "e2e" tests and must use the marker.

# Comments

- Only use comments when the flow between arrange and assert isn't obvious.
    - Typically, this is a code smell that the design is too complex
    - However, when a dependency has a non-obvious API or design choice, it can be helpful to call it out
    - Don't mark the arrange / act / assert blocks with comments unless they are lengthy and complex (to be avoided)
