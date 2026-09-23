# Python and Pattern authoring boundary

> 2026-09-22 · 目前的 working conclusion。這份 thought 收斂 Functional Python、Hybrid
> temporal primitives 與 Python-native Pattern algebra 的 disposable probes。它決定第一版
> authoring responsibility boundary，但不宣稱音樂品質、大型 production 或 lazy/infinite
> pattern 已被驗證。

## 結論

Tactus 應維持 **Python-first**。Production code 是 creative source of truth；Pattern algebra
是選用的局部標準函式庫，不是新的 production language、Arrangement schema 或
Strudel-style string mini-notation。

```text
Python creative policy
├── section and material functions
├── variant selection
└── one-off or semantic exceptions
             ↓
Optional local Pattern algebra
├── cycle and phase
├── Euclidean distribution
├── polymeter
└── periodic transformations
             ↓ realize(...)
tuple[Event, ...]
             ↓
Arrangement mechanics
└── place / repeat / scale_time
```

責任分界是：

- **Native Python** 擁有 creative policy、section/variant 選擇，以及一次性或語義性的例外。
- **Pattern functions** 擁有可命名、組合與重用的局部規律，例如 cycle、phase、Euclidean
  rhythm、rotation、reverse、polymeter 與 `every(n, transform)`。
- **Arrangement primitives** 擁有沒有創作立場、但每次都必須算對的 placement、repetition
  與 exact time transformation。
- Pattern 經 `realize()` 產生普通 Events；後續 arrangement 不需要知道 Events 原本來自
  Pattern、手寫 Python 或其他 generator。

一句話：

> Python 負責不規則的創作世界；Pattern functions 負責規律可以被命名、組合與重用的部分；
> 兩者最後都產生 Event，進入同一套 arrangement。

## 例外何時升級成 Pattern rule

一次性的例外留在 Python：

```python
variants = {3: "fill", 6: "fill"}

for bar_number in range(1, 7):
    groove(variant=variants.get(bar_number, "base"))
```

當例外本身形成穩定、可命名的週期時，才提升成 Pattern rule：

```python
rules = (
    every(3, rotating(1)),
    every(4, reverse),
)
```

判斷標準不是「能不能用數學寫」，而是該數學關係是否就是作品要保留的 creative intent。
只出現一次的 fill 不需要被偽裝成週期；每四個 cycles 發生一次的 transformation 則應保留其
週期關係。

## Probe evidence

### Hybrid authoring probe

六種 arrangement mutation 測試了 section relocation、one-off events、final repetition
variation、nonadjacent variants、density change 與 exact time scaling。最後的 Hybrid guide
六題皆 first-pass 通過，支持以下最小 temporal surface：

```python
bar(...)
bars(...)
beats(...)
place(...)
repeat(...)
scale_time(...)
```

這輪也顯示 Pattern class 不是一般 arrangement 的必要條件；`tuple[Event, ...]` 足以成為
material 與 arrangement 之間的邊界。

### Pattern algebra A/B probe

使用 `gpt-5.6-luna`、high reasoning effort，比較普通 Functional Python 與額外提供
Python-native Pattern functions 的三組 fresh tasks：

| Task | Functional Python | Pattern functions | Finding |
|---|---:|---:|---|
| Euclidean rhythm + rotation | first-pass PASS · `+8/-2` | first-pass PASS · `+14/-4` | 已有清楚 helper 時主要是 ownership relocation |
| 5/7-step polymeter | first-pass PASS · `+4/-5` | first-pass PASS · `+3/-4` | `stack()` 直接保存獨立 cycle 與 phase |
| Composed periodic transforms | first-pass PASS · `+11/-3` | first-pass PASS · `+9/-3` | `every(...)` 明示週期與 transform order |

兩組皆 3/3 first-pass。Pattern 沒提高這些小型任務的正確率；它的收益是把通用數學移出
production source：三題 final source 從 Functional 的 77 行降為 Pattern 的 56 行，production
source 裡的 modulo operations 從 5 個降為 0。這符合 framework 的既有責任原則：Agent 選擇
何時使用哪個規律，framework 實作反覆需要算對的已知算法。

## Candidate surface, not API commitment

Probe 使用了以下概念來確認表達力：

```python
from_steps(...)
euclidean(...)
rotate(...)
reverse(...)
stack(...)
every(...)
realize(...)
```

這份清單是實驗成功的 vocabulary，不是已拍板的 public API。第一版只應在真實 production
再次出現相同數學時提升 primitive；單一 production 的 task-specific pure function 仍是有效解法。

如果實作 Pattern value，它應是 framework 內部的輕量 local representation，用來保存 step
count、cycle length 與 transformation composition。它不應擴張為 Track、Section、Project 或
整首 Arrangement 的共同 schema。

## 尚未驗證

這輪沒有回答：

- Pattern 是否改善主觀音樂品質或自主創作。
- Probability、randomness 與 seed identity 應如何進 source of truth。
- Lazy／infinite Pattern 是否比 finite realization 更適合 audition。
- 大型 production 或長 session 中，Pattern expressions 是否更容易維護。
- Pattern evaluation、cache 與 incremental realization 是否值得自己的 compiled graph。
- Mini-notation 是否對人類 live coding 有價值；Tactus 目前沒有這個需求。

因此下一步不是先建立完整 Pattern subsystem，而是在真實 production 碰到第二個 consumer 時，
把已重複的數學提升成最小 primitive，並保持 `realize(...) -> tuple[Event, ...]` 這條邊界。
