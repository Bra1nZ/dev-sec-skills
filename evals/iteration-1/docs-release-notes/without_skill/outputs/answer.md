# rbac 1.4.12

## Summary

rbac 1.4.12 includes a CE-3 fix for a context leak, makes CE-4 fail closed for configurations outside the supported set, and documents CE-7 as PARALLEL RESTRICTED. The verification status below separates completed evidence from items that were not verified for this release.

## Changes

- **CE-3:** Fixed a context leak by dropping context before `RAISE`.
- **CE-4:** Now fails closed for out-of-supported configurations.
- **CE-7:** Documented as PARALLEL RESTRICTED.

## Verification

- `t/131`: 10/10 passed.
- Full `installcheck`: 876/876 passed on PostgreSQL 14-17.
- ASAN: 866/866 passed before CE-3. ASAN was not rerun after CE-3, so no post-fix ASAN result is claimed for this release.

## Not Verified

- A stale worker after secret rotation is unverified. No fix or guarantee is claimed for this scenario.
- Testing did not cover unsupported configurations; CE-4 is intended to fail closed in those cases.
