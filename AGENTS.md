<!-- agent-context:managed:start -->
## Engineering

1. The installed `ponytail` skill defines the default approach for every coding, debugging, refactoring, review, design, dependency, and implementation task. Apply it silently unless the user explicitly disables it; do not announce the skill or explain its internal method.
2. Project instructions, accepted decisions, architecture, safety requirements, and verified implementation take precedence over generic skill guidance. Surface a conflict instead of silently overriding project context.
3. Treat existing code as the source of truth for implemented behavior, and accepted specifications, decisions, architecture, and designs as the source of truth for intended behavior. Surface any disagreement instead of silently choosing one.
4. Read relevant accepted documentation before implementing a material feature. Resolve and document material architectural choices before implementation; do not use implementation work to make silent architectural decisions.
5. Respect documented module, component, service, data-access, and interface boundaries. Reuse established shared types, schemas, clients, services, and utilities when appropriate; do not bypass layers for a convenient shortcut.
6. Introduce a new architectural pattern, service, framework, infrastructure component, helper, or abstraction only when there is a demonstrated need. A single use is not enough unless it clearly improves correctness or readability.
7. Remove dead or temporary code introduced by the current change. Report unrelated problems without changing them unless they are in scope or approved.
8. Normally implement one defined roadmap task at a time. Completing it does not authorize silently continuing to the next task.
9. Do not infer implementation from repository layout or target documentation. Verify it in code and current-state evidence; label legacy, temporary, transitional, current, and target state clearly.

## Repository responsibilities

Prefer `apps/` for independently runnable or deployable components, `packages/` for genuinely shared code, `infra/` for repository-wide infrastructure, and `docs/` for durable project knowledge. Apply this as a preferred model, not as justification for unnecessary restructuring.

1. Root files normally govern the whole repository. Keep application-specific code, tests, runtime configuration, manifests, migrations, and Dockerfiles with their owning application when appropriate.
2. Create `apps/`, `packages/`, `infra/`, `scripts/`, or root `tests/` only for a real responsibility. Keep component tests near the component; reserve root `tests/` for repository-wide integration, acceptance, end-to-end, or fixture concerns.
3. Use `scripts/` for small repeatable operational automation, not architectural code. Keep database migrations with the component that owns the schema.

## Reproducibility

1. Treat runtime-version files, manifests, lockfiles, workspace configuration, containers, setup documentation, and CI as one toolchain consistency boundary. Respect pinned versions and do not regenerate lockfiles or change runtimes incidentally.
2. When complete lockfiles exist, use frozen or locked dependency installation. Keep documentation, CI, containers, manifests, and version files aligned.

## Command interface

When project complexity justifies it, maintain one short, documented command interface for recurring human and agent workflows. A root Makefile is the preferred interface for new multi-application or multi-tool projects unless another established task runner better fits the repository.

1. Create command targets only for real workflows. Prefer focused targets while iterating and an aggregate validation target before completion.
2. Keep Makefiles or other task runners readable. Move complex reusable logic into project scripts while preserving the target as the canonical entry point; do not add another abstraction for a simple one-line command.
3. Do not hide destructive behavior behind ambiguous commands. Use explicit names, document deletion and recovery, keep non-destructive shutdown separate from reset, and never make destructive work a dependency of routine setup, development, or validation.
4. The command interface is living project infrastructure. Update it with affected applications, paths, tooling, lockfiles, Docker or Compose configuration, CI, documentation, and workflows; do not leave a permanent manual bypass for a broken canonical command.

## Tooling defaults

1. In a new Python project, prefer `uv`. In an existing Python project, respect its package manager and lockfile.
2. In a new JavaScript or TypeScript project, use Volta to pin Node and tool versions, and use `pnpm` for project dependencies and scripts.
3. Volta and `pnpm` are complementary: Volta manages Node and tool versions; `pnpm` manages project dependencies and scripts.
4. In an existing JavaScript or TypeScript project, never change the package manager automatically.
5. Do not install `uv`, Volta, Node, or `pnpm` globally without explicit authorization.

## Workflow

1. Before material work, inspect relevant project instructions, `README.md`, `docs/README.md`, original requirements, accepted decisions, current and target architecture, relevant designs, implementation state, roadmap item, Git branch, and local changes when they exist. Inspect only the context needed for the task.
2. Follow the project's existing conventions, architecture, and tools.
3. Execute directly when the request is clear. Create a plan only when the work is genuinely architectural, ambiguous, or extensive; do not require a `PLAN.md`.
4. Keep changes in scope. Do not make opportunistic refactors, reformat unrelated lines, or replace manual changes without first understanding them.
5. Run relevant tests, linters, or checks after changes. Clearly state any verification that could not run.
6. Do not commit, push, amend, perform destructive resets, or force-push without explicit instruction. Never bypass hooks or checks with options such as `--no-verify`.
7. Confirm before deleting important files, data, or resources. Never include secrets, tokens, credentials, private company information, or sensitive data.
8. Consider work complete only when the requested change is implemented, validated, and limited to the correct scope.

## Documentation-first work

1. When a project is being defined, preserve original information separately from interpretation; identify requirements, contradictions, missing information, and unresolved decisions.
2. Record material decisions explicitly, update accepted architecture after decisions, add designs only for complex work, and keep implementation state and roadmap current. Do not start coding merely because a repository exists.
3. Begin implementation only when one next roadmap task is sufficiently defined and unblocked.
4. Use only relevant installed skills and read only the needed `SKILL.md` files and references. Project rules, accepted decisions, architecture, and implementation override generic skill guidance. Surface a conflict before applying a skill that would replace a project decision.
5. For a new or lightly structured project, inspect available context and existing documentation, classify it by responsibility, and create only structure supported by real information. Mark uncertainty as a proposal and ask for a decision when material ambiguity prevents safe progress.
6. For an established project, inspect existing structure, documentation ownership and links, current-versus-target ambiguity, duplication, and impacts on imports, builds, manifests, containers, CI, deployment, tests, scripts, and documentation. Before moving, renaming, consolidating, retiring, or deleting content, present a numbered proposal with classification, current and proposed state, reason, benefit, impact, risk, and required validation; include preserve or no-change items when appropriate, then obtain approval for the relevant items.

## Explicit readiness assessment

1. Perform this assessment only when the user explicitly asks whether the project or a specific task is ready to implement, or explicitly asks for a readiness assessment. Do not classify an ordinary project summary, current-state report, architecture overview, implemented-versus-missing review, roadmap summary, or next-step question as readiness.
2. Assess readiness for the requested task: relevant source context or requirements, accepted material decisions, accepted target architecture, detailed design when needed, verified current behavior, one concrete unblocked Next implementation item, validation commands, required skills, limitations and blockers, task scope, and the relevant canonical command interface when complexity justifies one.
3. Readiness is task-sensitive: a repository may be ready for an isolated change but not an architectural implementation. Do not claim readiness because instructions, a `docs/` directory, a roadmap, a directory, or target documentation exists. Verify current behavior in code and current-state evidence.
4. A readiness question alone does not authorize creating or reorganizing files. When implementation is not ready, identify the actual gap, present one contextual proposal with exact create, move, rename, consolidate, or preserve actions and reasons, then ask one focused approval question. Do not offer generic modes, empty directories, or speculative placeholders.
5. For a Makefile-based project, inspect `make help` or its default help target, the command for the next task, focused and aggregate validation targets, documentation alignment, and whether the interface is current. The presence of a Makefile alone does not prove readiness; its absence is not a failure for a simple project.

## Implementation task cycle

1. Read the current roadmap item and directly related decisions, architecture, and design; confirm the current implementation and identify files and validation commands in scope.
2. Implement only that task. Run the smallest relevant checks while iterating, then the applicable aggregate project check.
3. Update affected documentation and current implementation state. Move completed work into roadmap history with date and validation evidence, then promote one unblocked next item when appropriate.
4. Do not implement the newly promoted item unless explicitly requested.

## Project commands and validation

1. Inspect the repository's established command interface before executing raw commands. Prefer it, such as a Makefile, task runner, package scripts, or project scripts; use `make help` or the equivalent discovery command when available, and do not manually duplicate long commands when an equivalent project command exists.
2. Fix the root cause of a validation failure; never weaken or bypass validation to obtain a pass. Rerun the failed specific check, then the relevant aggregate check.
3. Distinguish existing failures from failures introduced by the current work. Never report validation as passed when it was not run; state what was skipped and why.
4. Setup must be safe to rerun where practical: preserve local configuration, credentials, and data; state platforms, prerequisites, required versions, verification commands, and any shell or `PATH` refresh. Distinguish setup from destructive reset.
5. When complexity justifies it, prefer one documented command interface for setup, development, validation, migrations, data preparation, and local deployment operations. Use its canonical commands, keep README, testing documentation, and CI aligned, and provide a discoverable help or command-listing mechanism.
6. Use focused canonical targets while iterating and the applicable aggregate target before completion. Inspect underlying commands when diagnosis requires it, but fix the canonical command or its dependencies rather than permanently bypassing it.
7. For a new multi-application or multi-tool project, consider a root Makefile when it adds real value. For an established project, preserve a suitable Makefile, Taskfile, justfile, package scripts, tox, nox, mise tasks, or other runner; propose and obtain approval before replacing or materially consolidating it.
8. When implementation changes recurring workflows, review the command interface, scripts, README, testing and operations documentation, CI, version files, lockfiles, Docker or Compose configuration, environment examples, paths, and help output that the change affects.
9. When changing behavior or invariants protected by repository checks, update the corresponding validation in the same change. Do not remove or weaken a failing check merely to obtain a pass; update it deliberately when the accepted behavior changes.

## Documentation

1. Repository documentation is durable shared state for the user, agents, sessions, implementation, and future maintainers. Important decisions, implementation state, limitations, and next work must not exist only in conversation memory.
2. Use `docs/` when a project needs more than a root README. The complete model guides. The project context decides. Create only what the project genuinely needs; do not create empty areas, speculative placeholders, or a document solely because it appears in a reference model.

## Documentation flow

Original information → extracted facts, requirements, contradictions, and ambiguities → explicit decisions → accepted architecture and relevant designs → verified current implementation state → one next roadmap task → implementation and validation → updated current state and roadmap.

1. Preserve useful original source files without editing them to fit the final direction. Keep facts, requirements, constraints, ambiguities, contradictions, and source references separate from interpretations; an extraction document may record them. Do not treat every source statement as an accepted decision or store sensitive material without need and appropriate handling.
2. Accepted decisions and architecture resolve source material. Preserve traceability from derived requirements and conclusions to the relevant original information.
3. Existing code and verified current-state evidence describe current behavior. Accepted architecture and design describe intended behavior. Keep the gap explicit; do not rewrite target architecture to make partial implementation appear compliant or describe temporary migration behavior as the destination.

## Canonical ownership

Read the document that owns the question. Other documents should link to it instead of duplicating changing information.

1. Root `README.md` owns project purpose, concise current status, high-level structure, requirements and toolchain, primary setup, run and validation commands, important limitations, links to detailed documents, and direction to future work. It is a map and entry point, not a duplicate of architecture, contracts, testing policy, roadmap, or runbooks.
2. `docs/original-information/` owns preserved requirements and source facts; `docs/decisions/` owns material rationale and status, including superseded-decision history and explicitly deferred re-evaluation conditions; `docs/architecture/` owns intended structure; and `docs/design/` owns detailed intended feature behavior.
3. `docs/implementation/current-state.md` owns verified current behavior, evidence, and limitations; `docs/implementation/roadmap.md` owns changing implementation priority and the next task; `docs/operations/` owns repeatable setup, configuration, deployment, and maintenance. An optional `docs/status.md` is a concise orientation dashboard that links to canonical current-state, roadmap, and blocker details. It does not replace verified evidence or implementation priority.
4. The selected task runner owns available command names and their implementation; project scripts own complex reusable command logic; CI owns CI execution while remaining semantically aligned with canonical local commands. Running or generated OpenAPI owns exact HTTP contracts when available. A dedicated `docs/testing/README.md` owns validation selection and interpretation when the project needs one. Adapt ownership to the actual project.

## Areas and handoff

1. When an active documentation area needs several files, add a useful local `README.md` that explains its purpose, what belongs and does not belong there, its canonical responsibility, relationships, update triggers, and duplication risks.
2. Projects may add areas such as `api/`, `testing/`, `security/`, `data/`, or `product/` when genuinely needed. Do not create inactive areas.
3. An implementation task is not complete until the durable project handoff is accurate. When the project uses these documents, record verified behavior, validation evidence, limitations, the completed roadmap item and date, exactly one promoted unblocked next item, remaining work, blockers, and links to affected decisions, architecture, design, and operations.
4. Do not copy the changing next task into multiple documents. The roadmap owns implementation priority.
5. The command interface is durable, living project knowledge. Keep its task runner, scripts, root README, testing documentation, operations documentation, and CI aligned when recurring workflows change.

## Consistency

1. Update affected documentation in the same change as the behavior it describes. Clearly distinguish original information, proposals, accepted decisions, current and target architecture, design, verified implementation, and planned work.
2. When an executable or generated artifact reliably defines low-level details, document its intent, ownership, boundaries, usage, constraints, and how to inspect it rather than manually duplicating the specification. Do not use this to omit important intent, security boundaries, workflows, or operational requirements.
3. Keep README files consistent with actual commands and review complete scope before finishing. Write technical repository documentation in English unless the project explicitly uses another language.

## Communication

1. Treat installed skills, instruction files, memory, context loading, and internal planning as invisible implementation details. Apply them silently. Do not mention skill names, instruction-file names, context setup, memory, prompt routing, or how reasoning is organized unless the user explicitly asks about agent configuration or a real conflict or blocker requires disclosure.
2. Communicate only project-relevant actions, decisions, results, risks, blockers, and next steps. Do not narrate reading instructions, selecting skills, routine context inspection, internal checklists, or ordinary safeguards. When a harness requires progress updates, describe the project action or result without exposing the internal mechanism.
3. The installed `i-have-adhd` skill defines the default response shape. Apply it silently unless the user explicitly asks for normal mode. Higher-priority instructions, safety requirements, and the user's requested level of explanation take precedence.
4. During work, report only meaningful state changes or decisions the user can act on. Distinguish proposed documentation, pending decisions, accepted decisions, implementation in progress, and verified completed implementation without explaining the internal framework used to make that distinction.
5. For completed implementation work, state the project behavior changed, affected documentation, validation result, commit or push status when relevant, remaining project limitation, and next project action when one exists. Mention a command-interface failure or skipped validation only when it affects confidence or requires action.

## Explicit readiness assessments

1. Use the readiness format only when the user explicitly asks whether the project or a specific task is ready to implement, or explicitly requests a readiness assessment. A project summary, status report, architecture overview, request for implemented versus missing behavior, or question about the next step is not a readiness request.
2. For an explicit readiness request, begin with a direct yes or no in the user's language. Ground the answer in verified project evidence and report only the readiness conclusion, the next project action, and actual blockers or limitations.
3. Do not include generic methodology slogans, documentation-model labels, skill inventories, instruction details, or internal context in a readiness answer unless the user explicitly requests that information.
<!-- agent-context:managed:end -->

# Repository agent instructions

## Initial Mac Mini sync

Before starting every task, update the checkout on the Mac Mini:

```bash
ssh sebs-macmini 'cd /Users/seb/Projects/forecast-engine && git pull'
```

If the pull reports conflicts, inspect the remote working tree, understand both
sides, and resolve the conflicts without discarding either intentional change.
Complete the merge or rebase and run the relevant checks before proceeding. If
the intent cannot be determined safely, stop and ask the user instead of deleting
changes. Never use `reset --hard` or force-push to resolve a sync problem.

The `cd` must remain inside the quoted SSH command; running `ssh sebs-macmini &&
cd ...` changes directory locally after the SSH session exits.

## Project conventions

- Use the `git` command for repository operations, including sync, branches,
  commits, and pushes. Do not use the GitHub CLI (`gh`).
- Keep the REST layer small; forecasting behavior belongs to the public
  `forecast_engine` package, while the official `chronos-forecasting` package
  owns Chronos model behavior and internals.
- Preserve the request and response contract documented in `README.md` and the
  generated `/openapi.json` schema.
- Add dependencies only when the standard library or an existing dependency does
  not cover the requirement.
- Run `uv run pytest` after code changes.
- Never commit model weights, caches, virtual environments, or secrets.
