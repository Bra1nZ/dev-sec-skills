# evidence-first-docs

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: agent skill](https://img.shields.io/badge/format-SKILL.md-orange)](SKILL.md)
[![Focus: evidence before claims](https://img.shields.io/badge/focus-evidence%20before%20claims-2ea44f)](SKILL.md)

Скилл для агентов, которые пишут и ревьюят техническую документацию:
README, архитектурные документы, ADR, API-контракты, security/compliance
разделы, release notes, audit packs и handoff-записки.

Он нужен там, где текст обещает больше, чем проверено. «Система безопасна»,
«всё протестировано», «соответствует стандарту», «гарантирует целостность» —
это не утверждения, пока рядом нет механизма, доказательства, области действия
и честного статуса.

## Главная мысль

Документация — это не рассказ о системе, а **claim ledger**. Каждое
материальное утверждение должно быть прослеживаемо до механизма и
доказательства, а ограничения должны стоять там же, где обещание.

У каждого claim'а четыре обязательных поля:

1. **Механизм** — что в системе должно делать утверждение истинным.
2. **Доказательство** — proof, model, test, analysis report, trace, benchmark
   или review record.
3. **Область** — где claim применим и что вне trust boundary.
4. **Статус** — самый сильный честный ярлык, который подтверждает evidence.

Нет одного из четырёх — нет claim'а. Есть намерение, план или открытый
вопрос. Их можно оставить в документе, но нельзя выдавать за результат.

## Статусы

| Статус | Что означает |
| --- | --- |
| `proven` | Машинно-проверенное доказательство свойства при явных допущениях и TCB |
| `model-checked` | Исчерпывающее или ограниченное исследование модели; указана граница и разрыв модель–код |
| `tested` | Выполненные тесты, которые пытались нарушить claim, с окружением и результатом |
| `static-refinement` | Статический анализ или refinement check; указаны инструмент, правила и нерешённые находки |
| `reviewed` | Только человеческое ревью, без исполняемого или формального evidence |
| `open` | Claim есть, доказательства нет; это риск, а не результат |

Понизить статус — не провал. Завысить — провал.

## Что внутри

- `SKILL.md` — workflow, claim ledger, статусы, scope/TCB, evidence strength,
  review checklist, антипаттерны.
- [`references/banned-words.md`](references/banned-words.md) — loaded words
  в английском и русском, нормативные `MUST/SHOULD/MAY`, замена vague
  quantifiers.
- [`references/evidence-template.md`](references/evidence-template.md) —
  шаблоны claim ledger, evidence index, release note, review record,
  negative-result record.

## Когда применять

- Перед публикацией README или архитектурного документа.
- Перед release notes, где нужно отделить поддержанные claims от открытых
  рисков.
- Перед аудитом или сертификацией, где нужен evidence pack.
- При ревью security/compliance текста: «secure», «compliant», «certified»,
  «guaranteed» без scope.
- При разборе инцидента: обновить claim ledger и добавить negative result,
  а не только красивый postmortem.

## Пример

Плохо:

> Система безопасна и полностью протестирована. Все тесты проходят.

Хорошо:

> Роль Y не может писать в таблицу T на PostgreSQL 14–17 через HTTP, batch и
> admin API (тесты T-04..T-11, статус `tested`, суперпользователь и DBA вне
> модели). Известные ограничения: stale-worker после ротации секрета не
> проверен (`open`).

## Установка

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/evidence-first-docs ~/.config/opencode/skills/
```

Скилл активируется, когда документ утверждает, что что-то secure, correct,
complete, verified, tested, certified, compliant или guaranteed; когда нужно
ревью документации на неподтверждённые claims; когда текст должен выдержать
аудитора или инцидент.

## Связь с другими скилами

- [`negative-test-first`](../negative-test-first/SKILL.md) даёт evidence для
  статусов `tested` и `open`.
- [`invariant-first-code`](../invariant-first-code/SKILL.md) даёт механизм и
  enforcement point для claim'ов о коде.
- Crosswalk со стандартами — в
  [`references/standards-map.md`](../../references/standards-map.md).

## Лицензия

MIT — см. [LICENSE](LICENSE). Сторонние стандарты сохраняют свои
лицензии.
