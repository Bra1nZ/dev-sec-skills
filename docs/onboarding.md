# Bootstrap: поднять гейты в чужом репозитории

Как за один детерминированный прогон поставить в целевой репозиторий
линтеры, честные `open`-шаблоны реестра и леджера, CI-шаблоны и внешний
ключ, а затем провести первую запись evidence до зелёных гейтов.

## Статус и границы

- **Статус:** `tested` (C-02), 2026-11-08. Evidence: прогон
  `spec/pilots/dev-sec-skills/detectors/test_bootstrap_eval.py`, который
  запускает `evals/bootstrap/run_evals.py` на одноразовом git-репозитории;
  лог и якорь — в `spec/pilots/dev-sec-skills/runs/`.
- **Scope:** Python 3.11, PyYAML, OpenSSH `ssh-keygen`, git; один
  синтетический целевой репозиторий и stdlib-набор тестов. Продуктовый
  репозиторий этим прогоном не проверялся.
- **Что доказывает прогон:** bootstrap создаёт ожидаемые файлы, шаблоны
  проходят `cell_lint` и `claim_lint`, путь «прогон → `run_record` → якорь →
  `tested`» даёт зелёные `cell_lint`, `claim_lint`, `status_diff`, а
  подмена вендоренного файла, правка подписанного поля и повышение статуса
  без evidence ловятся.
- **Чего прогон не доказывает:** что тест в целевом репозитории относится к
  формулировке claim; что ключ не скомпрометирован; что CI-шаблон отработал
  на GitHub runner. Отдельно: C-13 остаётся `open` — держатель ключа может
  пере-подписать запись, а замена `allowed_signers` вместе с новой подписью
  обходит проверку. Прозрачного журнала, timestamping и отзыва ключа нет.

## Что делает `tools/bootstrap.py`

Это планировщик и генератор, не запускатель тестов. Он:

1. копирует `tools/{claim_lint,cell_lint,status_diff,anchor_subject,anchor_run}.py`,
   `styles/` и `schemas/` без README, `spec/conveyor/cell-registry.schema.json`;
2. пишет `tools/dev-sec-skills.VERSION` — JSON с коммитом источника, флагом
   dirty и sha256 каждого вендоренного файла;
3. создаёт `spec/cells.yaml` и `docs/claims.yaml` в статусе `open`;
4. по `--with-ci` рендерит `.github/workflows/{claim,cell}-lint.yml` из
   `ci/`, подставляя пути и `FIRST_RELEASE=1`;
5. по `--with-anchor` создаёт или переиспользует ключ ed25519 **вне**
   репозитория и коммитит только публичную половину в
   `spec/anchor/allowed_signers`.

Он **не** запускает тесты, не пишет evidence и не поднимает статусы. Шаблоны
`open` — это форма записи, а не покрытие: создание леджера ничего не
доказывает о целевом коде.

## Требования

- Python 3.8+ и PyYAML: `pip install pyyaml`.
- `git` (нужен для `run_record.commit` и `status_diff`).
- `ssh-keygen` из OpenSSH (нужен для якорей).
- Опционально Vale 3.26.0: если он есть в `PATH`, `claim_lint` использует
  `styles/RussianAbsolutes`; иначе остаётся встроенный сканер.

## Быстрый старт

Целевой каталог должен существовать. Команда ниже запускается из любого
места: `--source` по умолчанию указывает на checkout, из которого запущен
скрипт.

```bash
python3 /path/to/dev-sec-skills/tools/bootstrap.py \
  --target ../my-service \
  --name my-service \
  --suite-glob 'tests/*.py' \
  --with-ci \
  --with-anchor
```

Полезные варианты:

```bash
# только план, без записи
python3 tools/bootstrap.py --target ../my-service --dry-run

# обновить вендоренные линтеры после обновления dev-sec-skills
python3 tools/bootstrap.py --target ../my-service --force

# другой каталог ключа (по умолчанию ~/.config/dev-sec-skills/anchor)
DEV_SEC_SKILLS_ANCHOR_DIR=/secure/keys \
  python3 tools/bootstrap.py --target ../my-service --with-anchor
```

`--force` обновляет вендоренные `tools/`, `schemas/`, `styles/` и
отрендеренные CI-файлы. Он **никогда** не перезаписывает `spec/cells.yaml` и
`docs/claims.yaml`: это evidence, и bootstrap, который умеет стирать
evidence, — это дефект, а не удобство.

## Что появляется в целевом репозитории

```text
tools/
  claim_lint.py  cell_lint.py  status_diff.py
  anchor_subject.py  anchor_run.py
  dev-sec-skills.VERSION
styles/                      # без README.md
schemas/                     # без README.md
spec/
  conveyor/cell-registry.schema.json
  cells.yaml                 # один open-cell, не покрытие
  anchor/allowed_signers     # только публичные ключи
docs/
  claims.yaml                # один open-claim, evidence: []
.github/workflows/
  claim-lint.yml  cell-lint.yml   # только с --with-ci
```

Bootstrap печатает Makefile-сниппет (`make verify`, `make cells`,
`make claims`, `make status`) и чек-лист. Сниппет — отправная точка;
подставьте свой `SUITE_GLOB` и свой release-ref.

## Первый зелёный прогон

Шаблоны уже проходят гейты, потому что claim и cell честно `open`:

```bash
python3 tools/cell_lint.py --root . --ledger docs/claims.yaml \
  --suite-glob 'tests/*.py' spec/cells.yaml

python3 tools/claim_lint.py --root . --suite-glob 'tests/*.py' \
  --run-log-root . --tool-output-root . docs/claims.yaml
```

`cell_lint` может показать info об неиспользуемых классах таксономии; это не
ошибка. `claim_lint` на open-шаблоне не показывает ничего.

## Путь повышения статуса

Порядок важен: сначала артефакт и прогон, потом запись, потом якорь, и
только потом статус.

1. Замените пример `CELL-001` на реальный инвариант: `entry_points`,
   `failure_mode`, `residual_risk`, `limitations`. Пока детектора нет,
   `coverage_status: open`.
2. Замените `C-01` на формулировку, которую проверяет конкретный тест.
   Оставьте `status: open` и `evidence: []`.
3. Запустите тест так, чтобы лог называл каждый тест и давал машинный
   итог. Для pytest: `pytest -v` (или `-rA`); для stdlib:
   `python3 -m unittest -v tests.test_smoke`.
4. Сохраните лог в репозиторий и посчитайте хэши:

   ```bash
   mkdir -p docs/runs
   python3 -m unittest -v tests.test_smoke \
     > docs/runs/unittest-2026-11-08.log 2>&1
   sha256sum docs/runs/unittest-2026-11-08.log tests/test_smoke.py
   git rev-parse HEAD
   ```

   Коммит должен содержать финальную версию артефакта: `claim_lint` L2
   сравнивает рабочий файл с блобом на указанном коммите и падает, если
   файл изменился после него.
5. Добавьте в claim `evidence` с `kind: test`, `tests`, `command`,
   `artifact`, `commit`, `date` и `run_record`. В `run_record` обязательны
   `runner`, `command`, `commit`, `exit_code`, `started_at`, `finished_at`,
   `log`, `log_sha256`, `artifact_sha256`, `tests_run`, `tests_passed`.
   Дата `finished_at` должна совпадать с `date` evidence.
6. Подпишите запись и вставьте напечатанный блок `anchor:` в `run_record`:

   ```bash
   python3 tools/anchor_run.py create \
     --ledger docs/claims.yaml --claim C-01 --channel run-record --run 0 \
     --key ~/.config/dev-sec-skills/anchor/key \
     --signer my-service-anchor-2026-11-08 \
     --out-dir spec/anchor \
     --allowed-signers spec/anchor/allowed_signers \
     --id run-record-my-service-c01-2026-11-08 --base .
   ```

7. Поднимите `status` claim и `coverage_status` ячейки до `tested`, добавьте
   детектор в ячейку и закоммитьте evidence, лог, `spec/anchor/*.json*` и
   правки леджера одним коммитом.
8. Прогоните оба линтера и `status_diff`:

   ```bash
   python3 tools/status_diff.py --repo . --ledger docs/claims.yaml \
     --git-ref <base-ref> [--first-release]
   ```

`status_diff` разрешает `open -> tested`, только если у claim появилась
новая запись evidence; повторная датировка того же evidence повышение не
поддерживает.

### Про счётчики в логе

`claim_lint` L2 сверяет `tests_run`/`tests_passed` с итоговой строкой
pytest (`N passed`) или cargo. `unittest` печатает `Ran N tests`, которую
линтер не разбирает: запись проходит, но остаётся одно `L2 info` «counts not
cross-checked». Это видимое ограничение, а не ошибка. Если нужен полный
кросс-чек, используйте pytest с `-v`.

## Ключ и `allowed_signers`

- Приватный ключ по умолчанию лежит в
  `~/.config/dev-sec-skills/anchor`; путь переопределяется
  `DEV_SEC_SKILLS_ANCHOR_DIR` или `--anchor-dir`.
- `--anchor-dir` внутри целевого репозитория или внутри checkout
  `dev-sec-skills` отклоняется: приватный ключ не должен попадать в git.
- Один ключ может обслуживать несколько репозиториев. Подпись привязана к
  имени signer и namespace канала, поэтому для каждого репозитория
  используйте своё имя signer (`<name>-anchor-<date>`); `allowed_signers`
  дополняется строкой, а не перезаписывается.
- `--with-anchor` создаёт ключ и коммитит публичную половину. Подпись
  записи — отдельный шаг (`anchor_run.py create`).
- Потеря, ротация и отзыв ключа: `spec/anchor/README.md`.

## Вендоринг и дрейф

`tools/dev-sec-skills.VERSION` — единственный источник правды о том, какие
байты вендорены. Он хранит `source_commit`, `source_dirty` и sha256 каждого
файла. При повторном запуске bootstrap:

- совпадающие файлы остаются без изменений (mtime не трогается);
- изменённый вендоренный файл печатается как `DRIFT`, команда выходит с
  кодом 1 и **не** перезаписывает его без `--force`;
- `--force` возвращает байты источника, но не трогает реестр и леджер.

Не правьте вендоренные линтеры в целевом репозитории: локальная правка
исчезнет при следующем `--force`, а до него будет расхождением с
`VERSION`. Меняйте линтер в `dev-sec-skills`, коммитьте там, затем
перезапускайте bootstrap с `--force`.

README для `styles/` и `schemas/` намеренно не вендорятся: L5 сканирует
`*.md` и нашёл бы в них цитаты запрещённых слов.

## CI-шаблоны

`--with-ci` рендерит два workflow из `ci/`:

- `claim-lint.yml` — L1–L5 по леджеру и `status_diff` против release-ref;
- `cell-lint.yml` — CL1–CL6 по реестру, с опциональным леджером.

Подставляются `LEDGER`, `REGISTRY`, `SUITE_GLOB` и `FIRST_RELEASE=1`.
`BASE_REF`/`RELEASE_REF` по умолчанию `v1.0`; после первого тега поставьте
реальный ref и `FIRST_RELEASE=0`. `fetch-depth: 0` обязателен: `status_diff`
читает base-леджер из git.

В шаблонах остаются `actions/checkout@v4` и `actions/setup-python@v5`.
Это изменяемые refs; перед включением гейта пришпильте их к SHA — ровно то,
что проверяет D-PINNED-ACTIONS в этом репозитории. Bootstrap печатает об
этом предупреждение и не притворяется, что шаблон уже безопасен.

## Что зелёный гейт не доказывает

- Якорь фиксирует байты записи, а не её истинность: держатель ключа может
  пере-подписать, а замена `allowed_signers` и новая подпись обходят
  проверку (C-13).
- `claim_lint` сверяет хэши, коммит, дату и наличие теста в логе; он не
  проверяет, что тест проверяет формулировку claim. Это остаётся ревью.
- `cell_lint` проверяет форму и связи, а не то, что детектор ловит именно
  заявленный отказ. Для `security`/`correctness` нужен mutation fixture;
  документированная `mutation_exemption` — это заявление, а не проверка.
- L5 — проверка прозы. Она не делает утверждение истинным и не заменяет
  evidence.
- Bootstrap-eval синтетический: один временный репозиторий, stdlib-тесты,
  Linux. Другие раннеры, Windows и реальные продуктовые репозитории им не
  покрыты.

## Самопроверка

```bash
python3 evals/bootstrap/run_evals.py   # 4/4
make evals                             # включает bootstrap-eval
make detectors-self                    # D-BOOTSTRAP поверх того же eval
```

Eval проверяет: создание файлов и хэши `VERSION`; идемпотентность;
детекцию дрейфа и восстановление через `--force`; зелёные open-гейты;
полный путь до `tested` с якорем; запрет перезаписи леджера через
`--force`; падение на правке подписанного поля; падение `status_diff` на
повышении без evidence; отказ на target внутри источника и на ключ внутри
target.

## Диагностика

| Симптом | Что значит | Что делать |
| --- | --- | --- |
| `PyYAML is required` | нет зависимости | `pip install pyyaml` |
| `ssh-keygen is required` / `not found` | нет OpenSSH | установить `openssh-client` |
| `DRIFT tools/...` | вендоренный файл изменён | проверить правку; `--force` вернёт источник |
| `artifact ... does not exist at the cited commit` | коммит старше файла | закоммитить артефакт и указать этот коммит |
| `artifact ... changed after the cited commit` | файл правили после прогона | новый прогон и новый коммит |
| `finished_at date ... does not match evidence date` | разные даты | выровнять `date` и дату `finished_at` |
| `test ... is cited but not executed in the run log` | лог не называет тест | `pytest -v` / `unittest -v`, перезаписать лог |
| `counts ... disagree with log` | счётчики не совпали с итогом | пересчитать `tests_run`/`tests_passed` |
| `anchor subject does not describe this record` | поле изменили после подписи | откатить или пере-подписать |
| `not found in suite` | `--suite-glob` не покрывает файл | расширить glob, но не до всего репозитория |
| `CL2 ... has no mutation_fixture` | security/correctness без fixture | добавить fixture или документированную exemption |
| `L2 info ... counts not cross-checked` | раннер не даёт знакомый итог | использовать pytest `-v` или принять ограничение |

## Связанные документы

- `spec/conveyor/CONCEPT.md` — V2-38, C-13, C-02.
- `spec/anchor/README.md` — ключи, ротация, потеря.
- `spec/static-analysis/README.md` — канал static-analysis.
- `ci/claim-lint.yml`, `ci/cell-lint.yml` — исходные шаблоны.
- `spec/pilots/dev-sec-skills/` — self-pilot: реестр, леджер, детекторы.
