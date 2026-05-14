def test_import_outputs_module():
    # Regression test: outputs.py previously had an invalid import.
    import engine.outputs  # noqa: F401
