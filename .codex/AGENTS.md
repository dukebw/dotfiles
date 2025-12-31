## Principles
- **TDD bias:** red → green → refactor in tiny cycles.
- **Small slices:** independent, quickly verifiable, easy to roll back.
- **Evidence over assertion:** prefer concrete tests/commands to remove ambiguity.
- **Risk-aware autonomy:** read/build/test and HTTP(S) GET are fine; confirm before commits/pushes, env-changing installs, DB/service mutations, or network writes (POST/PUT/DELETE).
- **Conventions first:** match existing style and patterns unless there’s a compelling reason not to.

## Flow
1. **Frame objective:** problem, constraints, acceptance in a few lines.
2. **Propose slice:** likely files/modules, tests to run/add, acceptance & quick rollback.
3. **Execute & report:** minimal diff + key test output.
4. **Review & next step:** suggest the next tiny slice.
5. **Close:** summarize rationale, tests added/updated, follow-ups (if any).

## Safety rails
- **Free:** read-only navigation (`rg`, `git grep`, `fd/find`, AST/indexers), local builds/tests/linters/type-checks, HTTP(S) GET for docs/specs/releases/CVEs.
- **Confirm first:** commits/pushes, env-changing installs, DB/service mutations, network writes (POST/PUT/DELETE).
- **IAM changes:** use the `audio-cloze-iam-admin` assume-role profile (e.g., `aws --profile audio-cloze-iam-admin …`); avoid granting `iam:*` to the day-to-day CLI user.

## Modular notes
- Read `CLAUDE.md` in the working directory and parents up to `$MODULAR_PATH`.
- Follow `$MODULAR_PATH/docs/internal/CodingStandards.md`.
- Discover tests with Bazel queries (e.g., `./bazelw query | grep <pattern>`); run with `./bazelw test …`.
- `./bazelw test` does **not** accept `-q`.

## Agent protocol
- Bugs: add regression test when it fits.
- Keep files <~500 LOC; split/refactor as needed.
- Commits: Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
