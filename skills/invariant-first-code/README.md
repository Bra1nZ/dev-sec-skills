# invariant-first-code

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: agent skill](https://img.shields.io/badge/format-SKILL.md-orange)](SKILL.md)
[![Focus: fail closed](https://img.shields.io/badge/focus-fail%20closed-2ea44f)](SKILL.md)

Скилл для агентов, которые проектируют и ревьюят код с security,
correctness, integrity или availability claims: auth и права, хранение
данных, транзакции, миграции, конкурентность, API, секреты, lifecycle,
release и supply chain.

Он нужен там, где «мы добавили проверку» не означает «обойти нельзя». Guard
на одном пути — не свойство системы. Проверка, которая падает в allow, — не
проверка. Тест, который проходит и без guard'а, — не доказательство.

## Главная мысль

Код — это набор инвариантов, в которые кто-то верит. Сделайте их явными,
поставьте принуждение в одну точку и проверьте принуждение adversarially.

Для каждого инварианта нужно ответить:

1. **Statement** — что всегда должно быть истинно, в фальсифицируемых
   терминах.
2. **Enforcement point** — единственное место, которое предотвращает
   нарушение.
3. **Failure mode** — что происходит при отсутствии принуждения или ошибке:
   deny, abort, rollback или safe degrade. Никогда не allow-by-default.
4. **Evidence** — негативный тест, анализ или proof, показывающий, что
   попытка нарушения проваливается.
5. **Scope** — платформы, версии, акторы и пути, которые покрыты.

Нет enforcement point или violation test — это не инвариант, а пожелание.

## Что внутри

- `SKILL.md` — invariant map, fail-closed design, authorization, data и
  transaction invariants, concurrency, interfaces/errors, lifecycle/secrets,
  platform contracts, build/supply chain, verification, review checklist,
  антипаттерны.
- [`references/invariant-template.md`](references/invariant-template.md) —
  шаблон инварианта, карта и вопросы, которые вскрывают пропущенные
  инварианты.
- [`references/review-checklist.md`](references/review-checklist.md) —
  компактный чеклист для ревью security-чувствительных изменений.

## Ключевые правила

- **Default deny.** Ошибка, timeout, отсутствие policy, неизвестная роль или
  недоступный сервис не расширяют доступ.
- **Одна точка принуждения.** Policy не дублируется по handlers: копии
  расходятся.
- **Все пути.** HTTP, batch, import, admin API, background job, migration,
  recovery — один и тот же защищённый ресурс.
- **Object-level authorization.** Доступ к endpoint не означает доступ к
  каждому объекту.
- **Атомарность.** Check-then-act — гонка, пока проверка и действие не
  атомарны.
- **Fencing.** Stale worker не должен коммитить после потери lease.
- **No partial write.** Отказ не оставляет полусостояние.
- **Verify the verifier.** Удалите guard или замените его no-op: тест должен
  упасть. Иначе это не evidence.

## Пример

Плохо:

> Добавили проверку роли в HTTP-handler. Тесты проходят.

Хорошо:

> Инвариант I-01: ни одна запись в T не проходит без capability. Точка
> принуждения — `authorize_write()`; default deny при ошибке policy. Покрыты
> HTTP, batch, import, admin и migration. Роль Y, role-less, expired,
> соседний tenant и object-owner не проходят (T-04..T-11). Тест падает при
> удалении guard'а. Scope: PostgreSQL 14–17; superuser/DBA вне модели.

## Установка

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/invariant-first-code ~/.config/opencode/skills/
```

Скилл активируется, когда нужно спроектировать или отревьюить фичу, которая
не должна быть обойдена, не должна потерять или испортить данные, не должна
применить операцию дважды или должна fail closed.

## Связь с другими скилами

- [`negative-test-first`](../negative-test-first/SKILL.md) превращает каждый
  инвариант в попытку нарушения.
- [`evidence-first-docs`](../evidence-first-docs/SKILL.md) фиксирует
  механизм, evidence, scope и статус.
- Crosswalk со стандартами — в
  [`references/standards-map.md`](../../references/standards-map.md).

## Лицензия

MIT — см. [LICENSE](LICENSE). Сторонние стандарты сохраняют свои
лицензии.
