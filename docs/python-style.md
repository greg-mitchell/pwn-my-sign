# Python Style Guide

This is for source style. See [test-style.md](./test-style.md) for test-specific guidance

- Prefer dependency-injection patterns to provide stateful or side-effecting dependencies for better testability
- Use StrEnum or IntEnum to define closed sets of defined values. Prefer that over Enum to avoid having to call `.value`
- Use Pydantic Models in a data model first approach. Define the data, then the types that operate over them. Declare
  semantic constraints on the model. Use the model to own serialization instead of custom imperative serializers.
- Prefer using immutable data when possible. E.g. frozenset / frozendict, tuples or Sequence instead of list, etc.
- Do not use __init__.py files
- Each module should be focused and own one thing
- Do not use guarded imports. If you do need to use one (e.g. circular dep), this suggests the design is wrong.
    - Exception: typecheck guards