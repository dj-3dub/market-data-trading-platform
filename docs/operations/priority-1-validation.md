# Priority 1 validation record

Validation performed against the updated source on 2026-10-08.

| Check | Result |
|---|---|
| Python unit/contract tests | 24 passed |
| ShellCheck, warning severity, `scripts/*.sh` | Passed |
| Python compilation, services/scripts/tools/agent collector | Passed |
| Compose, workflow and monitoring YAML parsing | Passed |
| Dashboard JSON structure | Four valid dashboards |
| Make acceptance command order | Verified by dry run |
| Patch application to the original uploaded snapshot | Verified during packaging |
| Docker Compose resolved configuration and live acceptance | Not run: Docker unavailable |
| Live container recreation/persistence | Not run: Docker unavailable |
| .NET build/tests | Not run: .NET unavailable |
| Terraform validation/tests | Not run: Terraform unavailable |
| Prometheus rule execution | Not run: promtool/Docker unavailable |
| Native eBPF loading | Not run: compatible BCC/kernel environment unavailable |
| AWS deployment | Not run |

The Python suite includes mocked experiment orchestration and restoration,
credential generation/preservation, required local access/storage configuration,
and report provenance/secret exclusion. Passing those tests is not a live
storage guarantee. Execute `make acceptance` on the VM and inspect its evidence
before marking the runtime acceptance checklist complete.

The test run emitted an upstream FastAPI/Starlette TestClient deprecation warning.
No dependency upgrade is included in this milestone.
