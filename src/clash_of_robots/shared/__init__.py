"""Types and pure logic shared between the backend server and clients.

This package must not import from `server/` or `client/` — it is the
common base both layers sit on. Contents: protocol enums and payload
types, replay schema, player metadata, fog-of-war computation,
viewer-filter redaction.
"""
