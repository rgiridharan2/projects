"""Data-access layer: every SQL query lives here.

Repository functions take a Session, read or write rows, and never commit. The caller (a
router, the seed script, or a test) decides when the transaction ends, so several repository
calls can be committed together or rolled back together.
"""
