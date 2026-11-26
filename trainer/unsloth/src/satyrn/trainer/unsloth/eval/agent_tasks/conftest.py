"""The task folders hold starting code with seeded bugs and hidden tests that only make sense once copied into a
sample's workspace; keep pytest from collecting them when the repository's own tests run."""

collect_ignore_glob = ["*/*"]
