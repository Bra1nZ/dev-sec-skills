# Dev-Sec Skills: Evidence Before Claims

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: SKILL.md](https://img.shields.io/badge/format-SKILL.md-orange)](skills/negative-test-first/SKILL.md)
[![Languages: RU / EN](https://img.shields.io/badge/docs-RU%20%2F%20EN-2ea44f)](README.en.md)

Набор агентских скилов для команд, которым недостаточно зелёного теста и
уверенного текста. Здесь собран один рабочий принцип в трёх плоскостях:
**заявление существует только вместе с доказательством, областью действия и
честным статусом.**

Скилы не привязаны к языку программирования, фреймворку или конкретному
стандарту. Они описывают, как агенту думать и что проверять, а references
связывают эти правила с международными и российскими стандартами.

## Зачем это нужно

Агенты хорошо пишут позитивные тесты и убедительные README. Они проверяют,
что код делает то, о чём попросили, и почти никогда — что код отказывает
тому, о чём не просили. В результате появляется зелёный suite, который не
доказывает правило, и документ, который обещает больше, чем проверено.

Эти скилы переворачивают вопрос:

- не «фича работает?», а «какой тест попытался её нарушить?»;
- не «система безопасна?», а «кто именно не смог пройти и при какой модели
  угроз?»;
- не «всё протестировано?», а «какие claim'ы остались `open`, и кто это
  признал?».

## Три скила

| Скил | Когда применять | Главный результат |
| --- | --- | --- |
| [`negative-test-first`](skills/negative-test-first/SKILL.md) | Планирование тестов, проверка покрытия, решение «фича готова», релизный gate | Каждое требование связано с тестом, который пытается его нарушить |
| [`evidence-first-docs`](skills/evidence-first-docs/SKILL.md) | README, архитектура, ADR, API-контракты, security/compliance claims, release notes, audit pack | Claim ledger: механизм, evidence, scope, status, ограничения |
| [`invariant-first-code`](skills/invariant-first-code/SKILL.md) | Auth, права, данные, транзакции, миграции, конкурентность, API, секреты, supply chain | Инвариант, точка принуждения, fail-closed и негативная проверка |

Скилы дополняют друг друга:

1. `invariant-first-code` называет, что должно быть всегда истинно.
2. `negative-test-first` пытается это нарушить.
3. `evidence-first-docs` фиксирует, что именно доказано, где и с какими
   ограничениями.

## Общие принципы

- **Claim, а не настроение.** «Безопасно» и «корректно» — не утверждения.
  Утверждение должно быть фальсифицируемым.
- **Негатив первым.** Позитивный тест — дешёвая половина. Покрытие начинается
  с попытки нарушения.
- **Scope рядом с claim.** Версии, платформы, привилегированные акторы и
  исключения указываются там же, где обещание.
- **Статус, а не вера.** `proven`, `model-checked`, `tested`,
  `static-refinement`, `reviewed`, `open` — разные вещи.
- **Артефакт — не доказательство.** Наличие отчёта, теста или PDF не значит,
  что проверка что-то доказала. Нужен результат, область и воспроизводимость.
- **Стандарт-агностичность.** Ядро скилов не называет стандартов. Связь с
  ними — в отдельном crosswalk.

## Стандарты

Ядро опирается на инженерные практики, которые встречаются в NIST SSDF,
NIST SP 800-160, OWASP ASVS, ISO/IEC/IEEE 29148/42010/29119, ISO/IEC 25010,
CWE/SARIF, SLSA, SPDX/CycloneDX, RFC 2119/8174 и Diátaxis.

Российские требования — ФСТЭК 55, 76, 64 и ГОСТ Р 56939-2024 / 71207-2024 —
не растворяются в ядре. Они собраны в
[`references/standards-map.md`](references/standards-map.md) вместе с
международными аналогами. Это **crosswalk, а не сертификация и не аудит**:
соответствие стандарту нельзя объявлять по таблице.

Скачанные свободно доступные документы и ссылки на платные ISO — в
[`references/standards/SOURCES.md`](references/standards/SOURCES.md).

## Структура

```text
skills/
  negative-test-first/
    SKILL.md
    README.md
    README.en.md
  evidence-first-docs/
    SKILL.md
    README.md
    README.en.md
    references/
      banned-words.md
      evidence-template.md
  invariant-first-code/
    SKILL.md
    README.md
    README.en.md
    references/
      invariant-template.md
      review-checklist.md
references/
  standards-map.md
  standards/
    SOURCES.md
    downloaded/
evals/
  evals.json
  iteration-1/
    RESULTS.md
  iteration-2/
    evals.json
    RESULTS.md
```

## Установка

Скилы нейтральны к агенту: это каталоги с `SKILL.md`. Скопируйте нужный
каталог туда, где агент ищет скилы.

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/negative-test-first ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/evidence-first-docs ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/invariant-first-code ~/.config/opencode/skills/
```

Для другого агента положите `SKILL.md` и его `references/` в каталог скилов
этого агента. `README.md` рядом со скилом — для человека, не для загрузки в
контекст.

## Как пользоваться

- Перед релизом: прогоните `negative-test-first` по claim'ам и проверьте,
  какие из них не имеют нарушающего теста.
- Перед публикацией README или audit pack: прогоните `evidence-first-docs`,
  чтобы убрать неподтверждённые абсолюты и добавить scope.
- Перед merge security-чувствительного изменения: прогоните
  `invariant-first-code` по чеклисту и проверьте, что guard нельзя обойти и
  что тест падает при его удалении.
- При разборе инцидента: добавьте именованный урок в тест, а не только в
  комментарий.

## Языки

- `SKILL.md` — английский, чтобы скил работал в мультиязычных агентах.
- `README.md` — русский.
- `README.en.md` — английский.
- Внутри скилов нет языковых приложений: примеры и правила применимы к
  любому стеку.

## Статус

Это ранняя версия `0.1`: три скила, crosswalk, шаблоны evidence и два
eval-набора (шесть базовых задач и три near-miss). Результаты — в
[`evals/iteration-1/RESULTS.md`](evals/iteration-1/RESULTS.md) и
[`evals/iteration-2/RESULTS.md`](evals/iteration-2/RESULTS.md). В планах —
исполняемые проверки для статического анализа, линтеры для claim ledger и
trigger-eval. Пока это дисциплина и документация, а не сертификат и не
замена аудиту.

## Лицензия

MIT — см. [LICENSE](LICENSE). Сторонние стандарты сохраняют свои лицензии;
см. [`references/standards/SOURCES.md`](references/standards/SOURCES.md).
