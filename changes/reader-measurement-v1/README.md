# Reader measurement owner

Owner: scripts/build_reader_measurement_v1.py. Runtime source is the WordPress
plugin below; generated files are config/reader-allowlist.v1.json,
config/reader-runtime.v1.json, runtime-manifest.v1.json and theme-runtime-binding.v1.json.
Main copies the binding into its owned theme asset and stamps its exact digest;
this generator never writes the theme.

Run with .venv/bin/python -B scripts/build_reader_measurement_v1.py --generate,
then --check. --package checks current sources first and writes only the private
review artifact. No external service, production request, registration, installation
or approval occurs. --privacy-source accepts a repository-local block_markup
fixture only with --generate. It is not a runtime path or URL. The default fixed
source is changes/editorial-portfolio-v3/reader-measurement-privacy.html;
--check/--package always bind the current default source, so an override cannot
silently become a release policy. Regenerate only this owner.

Read wordpress-plugin/raos-reader-measurement/README.md for the public API,
manual activation/approval, exact browser config, cleanup handoff and admin steps.

Tests: PATH=/tmp/raos-reader-tools:/home/minami/.nvm/versions/node/v24.18.1/bin:/usr/bin:/bin
.venv/bin/python -B -m pytest tests/reader_measurement_v1 -q
--override-ini addopts=. PHP runs in the existing offline container wrapper.
Browser tests intercept and fulfill every request in a bounded local simulation;
the production-shaped origin is never contacted. These are automated checks,
not human approval, real reader comprehension evidence or production verification.
