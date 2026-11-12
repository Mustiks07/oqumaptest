/** One place for user-facing names of internal entities and codes.
 *
 *  Internal codes (T3, DEMO-M6-3.2, EDA, enum values such as `comparable` or `as_incorrect`) stay in the API and in
 *  the database for reproducibility. Screens show the human names below; a code is shown only inside
 *  "Технические сведения". Every component uses these helpers instead of ad-hoc string replacements. */
import { useMemo } from "react";
import { useCurriculum } from "../api/hooks";
import { useI18n } from "../i18n/I18n";
import type { DictKey, Lang } from "../i18n/dict";

export interface EditionLike {
  id?: string;
  code?: string | null;
  title?: string | null;
  name_ru?: string | null;
  name_kz?: string | null;
}

const EDITION_RE = /(пособие|учебник|оқулық|құрал)\s+([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ0-9]{1,3})\b/i;

/** Pedagogical names for distractor patterns. These codes remain stable in data, but never appear in the working UI. */
const MISCONCEPTION_NAMES: Record<string, { ru: string; kz: string }> = {
  add_across: { ru: "Складывает числители и знаменатели отдельно", kz: "Алымдары мен бөлімдерін бөлек қосады" },
  subtract_across: { ru: "Вычитает числители и знаменатели отдельно", kz: "Алымдары мен бөлімдерін бөлек азайтады" },
  numerators_not_scaled: { ru: "Не домножает числители при приведении к общему знаменателю", kz: "Ортақ бөлімге келтіргенде алымдарын көбейтпейді" },
  multiplied_instead: { ru: "Умножает вместо сложения", kz: "Қосудың орнына көбейтеді" },
  denominators_added: { ru: "Складывает только знаменатели", kz: "Тек бөлімдерін қосады" },
  mixed_subtract_reverse: { ru: "Вычитает меньшую дробную часть из большей, не занимая единицу", kz: "Бірлікті алмай, кіші бөлшек бөлігін үлкенінен азайтады" },
  borrow_error: { ru: "Ошибка при занимании единицы", kz: "Бірлікті алу кезіндегі қате" },
  ignore_fraction: { ru: "Не учитывает дробную часть", kz: "Бөлшек бөлігін ескермейді" },
  whole_part_error: { ru: "Ошибка в целой части", kz: "Бүтін бөліктегі қате" },
  whole_as_numerator: { ru: "Вычитает целое число из числителя", kz: "Бүтін санды алымнан азайтады" },
  answered_complement: { ru: "Находит оставшуюся часть вместо искомой", kz: "Ізделінді орнына қалған бөлікті табады" },
  wrong_operation: { ru: "Выбирает неверное действие", kz: "Амал дұрыс таңдалмаған" },
  calc_error: { ru: "Вычислительная ошибка без устойчивого шаблона", kz: "Тұрақты үлгісі жоқ есептеу қатесі" },
  gcd_lcm_confusion: { ru: "Путает НОД и НОК", kz: "ЕҮОБ пен ЕКОЕ-ні шатастырады" },
  incomplete_factorization: { ru: "Находит общий делитель, но не наибольший", kz: "Ортақ бөлгішті табады, бірақ ең үлкенін емес" },
  lcm_as_product: { ru: "Берёт произведение вместо наименьшего общего кратного", kz: "ЕКОЕ орнына көбейтіндіні алады" },
  lcm_as_sum: { ru: "Складывает числа вместо поиска НОК", kz: "ЕКОЕ табудың орнына сандарды қосады" },
  div3_vs_div9: { ru: "Путает признаки делимости на 3 и 9", kz: "3-ке және 9-ға бөлінгіштік белгілерін шатастырады" },
  last_digit_rule: { ru: "Проверяет делимость на 9 только по последней цифре", kz: "9-ға бөлінуді тек соңғы цифрмен тексереді" },
  partial_condition: { ru: "Проверяет только одно из условий", kz: "Шарттардың тек біреуін тексереді" },
  incomplete_simplification: { ru: "Сокращает дробь не до конца", kz: "Бөлшекті соңына дейін қысқартпайды" },
  inverted: { ru: "Переворачивает дробь", kz: "Бөлшекті аударып жазады" },
  denominator_only_scaled: { ru: "Изменяет только знаменатель", kz: "Тек бөлімін өзгертеді" },
  additive_scaling: { ru: "Прибавляет одно число к числителю и знаменателю", kz: "Алымы мен бөліміне бірдей сан қосады" },
  additive_equivalence: { ru: "Ошибочно определяет равные дроби по одинаковому приросту", kz: "Бірдей өсім бойынша бөлшектерді қате тең деп санайды" },
  compare_numerators_only: { ru: "Сравнивает только числители", kz: "Тек алымдарын салыстырады" },
  larger_denominator_larger: { ru: "Считает дробь с большим знаменателем большей", kz: "Бөлімі үлкен бөлшекті үлкен деп санайды" },
  cannot_compare_diff_den: { ru: "Считает, что дроби с разными знаменателями нельзя сравнить", kz: "Бөлімдері әртүрлі бөлшектерді салыстыруға болмайды деп санайды" },
  equal_difference: { ru: "Сравнивает дроби по разности числителя и знаменателя", kz: "Алым мен бөлім айырмасы бойынша салыстырады" },
  cross_multiplication: { ru: "Перемножает крест-накрест при умножении дробей", kz: "Бөлшектерді көбейткенде айқыш көбейтеді" },
  denominator_not_multiplied: { ru: "Не умножает знаменатели", kz: "Бөлімдерін көбейтпейді" },
  whole_multiplies_denominator_too: { ru: "Умножает на целое и числитель, и знаменатель", kz: "Бүтін санға алымын да, бөлімін де көбейтеді" },
  divide_no_reciprocal: { ru: "При делении не переходит к обратной дроби", kz: "Бөлгенде кері бөлшекке көшпейді" },
  reciprocal_wrong_fraction: { ru: "Переворачивает делимое вместо делителя", kz: "Бөлгіштің орнына бөлінгішті аударады" },
  reciprocal_of_answer: { ru: "Даёт число, обратное верному ответу", kz: "Дұрыс жауапқа кері санды береді" },
  additive_division: { ru: "Заменяет деление сложением", kz: "Бөлуді қосумен алмастырады" },
  fraction_of_number_divide: { ru: "Делит на дробь вместо умножения", kz: "Көбейтудің орнына бөлшекке бөледі" },
  only_divides_by_denominator: { ru: "Находит только одну долю", kz: "Тек бір үлесті табады" },
  only_multiplies_numerator: { ru: "Умножает на числитель, не деля на знаменатель", kz: "Бөлімге бөлмей, алымға көбейтеді" },
  decimal_digit_concatenation: { ru: "Записывает цифры дроби подряд как десятичную", kz: "Бөлшек цифрларын ондық бөлшек ретінде қатар жазады" },
  decimal_place_value: { ru: "Ошибка в разрядах десятичной дроби", kz: "Ондық бөлшек разрядтарындағы қате" },
  decimal_as_reciprocal: { ru: "Принимает десятичную дробь за обратную", kz: "Ондық бөлшекті кері бөлшек деп санайды" },
  decimal_align_right: { ru: "Выравнивает десятичные дроби по правому краю", kz: "Ондық бөлшектерді оң жақ шетіне теңестіреді" },
  decimal_point_count: { ru: "Ошибка в положении десятичной запятой", kz: "Ондық үтірдің орнын қате анықтайды" },
  decimal_longer_larger: { ru: "Считает более длинную десятичную дробь большей", kz: "Таңбасы көп ондық бөлшекті үлкен деп санайды" },
  ratio_order: { ru: "Меняет порядок членов отношения", kz: "Қатынас мүшелерінің ретін ауыстырады" },
  difference_not_ratio: { ru: "Использует разность вместо отношения", kz: "Қатынастың орнына айырманы қолданады" },
  part_part_instead_of_part_whole: { ru: "Сравнивает часть с частью вместо части с целым", kz: "Бөлікті бүтінмен емес, бөлікпен салыстырады" },
  proportion_additive: { ru: "Рассуждает сложением вместо пропорции", kz: "Пропорция орнына қосу арқылы пайымдайды" },
  cross_multiply_wrong: { ru: "Неверно применяет основное свойство пропорции", kz: "Пропорцияның негізгі қасиетін дұрыс қолданбайды" },
  inverse_proportion: { ru: "Использует обратную пропорциональность вместо прямой", kz: "Тура пропорционалдық орнына кері пропорционалдықты қолданады" },
  percent_as_number: { ru: "Использует число процентов как готовый ответ", kz: "Пайыз санын дайын жауап ретінде алады" },
  percent_divide: { ru: "Делит число на количество процентов", kz: "Санды пайыз санына бөледі" },
  divides_by_percent_fraction: { ru: "Делит на долю вместо умножения", kz: "Үлеске көбейтудің орнына бөледі" },
  percent_base_confusion: { ru: "Путает базу, от которой считается процент", kz: "Пайыз есептелетін негізді шатастырады" },
  difference_instead: { ru: "Использует разность вместо процентного отношения", kz: "Пайыздық қатынас орнына айырманы алады" },
  additive_percent: { ru: "Складывает проценты с числом", kz: "Пайызды санмен қосады" },
  answered_change_only: { ru: "Указывает изменение вместо нового значения", kz: "Жаңа мән орнына өзгеріс шамасын береді" },
  direction_error: { ru: "Путает увеличение и уменьшение", kz: "Арту мен кемуді шатастырады" },
};

/** "Демонстрационное пособие А" → "Пособие А" / "А оқу құралы"; the server sends the same names (name_ru/name_kz). */
export function editionName(e: EditionLike | null | undefined, lang: Lang): string {
  if (!e) return "—";
  const fromServer = lang === "kz" ? e.name_kz : e.name_ru;
  if (fromServer) return fromServer;
  const title = (e.title ?? "").trim();
  const m = EDITION_RE.exec(title);
  if (m) {
    const word = m[1].toLowerCase();
    const letter = m[2].toUpperCase();
    if (lang === "kz") return word === "учебник" || word === "оқулық" ? `${letter} оқулығы` : `${letter} оқу құралы`;
    return `${word === "учебник" ? "Учебник" : "Пособие"} ${letter}`;
  }
  return title || e.code || "—";
}

/** Dictionary key for an enum value, when it exists: label("comparability", "comparable"). */
export function enumKey(prefix: string, value: string | null | undefined): DictKey {
  return `${prefix}.${value ?? ""}` as DictKey;
}

export interface Labels {
  topic: (codeOrId: string | null | undefined) => string;
  objective: (code: string | null | undefined) => string;
  edition: (codeOrId: string | null | undefined) => string;
  misconception: (code: string | null | undefined) => string;
  /** replace any known code inside a server text with its human name */
  text: (s: string | null | undefined) => string;
  ready: boolean;
}

/** Names from the current programme (curriculum endpoint). Falls back to the code only while loading. */
export function useLabels(): Labels {
  const { lang } = useI18n();
  const cur = useCurriculum();
  return useMemo(() => {
    const d = cur.data;
    const topics = new Map<string, string>();
    const objectives = new Map<string, string>();
    const editions = new Map<string, string>();
    const misconceptions = new Map(Object.entries(MISCONCEPTION_NAMES).map(([code, names]) => [code, lang === "kz" ? names.kz : names.ru]));
    for (const t of d?.topics ?? []) {
      const name = (lang === "kz" ? t.title_kz : t.title_ru) || t.title_ru;
      topics.set(t.code, name);
      topics.set(t.id, name);
    }
    for (const o of d?.objectives ?? []) objectives.set(o.code, (lang === "kz" ? o.text_kz : o.text_ru) || o.text_ru);
    for (const e of d?.editions ?? []) {
      const name = editionName(e as EditionLike, lang);
      if (e.code) editions.set(e.code, name);
      editions.set(e.id, name);
    }
    const text = (s: string | null | undefined) => {
      if (!s) return "";
      let out = s;
      const replace = (map: Map<string, string>, quote: boolean) => {
        const codes = Array.from(map.keys()).filter((k) => k.length < 30).sort((a, b) => b.length - a.length);
        for (const code of codes) {
          const esc = code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          out = out.replace(new RegExp(`(?<![\\w-])${esc}(?![\\w.-])`, "g"), quote ? `«${map.get(code)}»` : map.get(code)!);
        }
      };
      replace(objectives, true);
      replace(editions, false);
      replace(topics, true);
      replace(misconceptions, false);
      return out.replace(/««([^»]*)»»/g, "«$1»");
    };
    return {
      topic: (c) => (c ? topics.get(c) ?? c : "—"),
      objective: (c) => (c ? objectives.get(c) ?? c : "—"),
      edition: (c) => (c ? editions.get(c) ?? c : "—"),
      misconception: (c) => (c ? misconceptions.get(c) ?? c.replaceAll("_", " ") : "—"),
      text,
      ready: !!d,
    };
  }, [cur.data, lang]);
}

/** Tokens that must never appear in the primary (non-technical) view. Used by tests and by a dev-only check. */
export const RAW_TOKENS = [
  "DEMO-M6", "cluster_robust_t_class", "target_hours", "adjusted_association", "comparable", "confirmed_only", "as_incorrect",
] as const;
