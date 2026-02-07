import { useEffect, useMemo, useState } from "react";

const clamp = (value: number, min: number, max: number) => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const useTypewriter = (
  phrases: string[],
  typeDelayMs = 80,
  deleteDelayMs = 40,
  holdDelayMs = 2000
) => {
  const safePhrases = useMemo(
    () => phrases.filter((phrase) => phrase.trim().length > 0),
    [phrases]
  );
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (safePhrases.length === 0) return;
    const current = safePhrases[phraseIndex % safePhrases.length];

    const delay = deleting ? deleteDelayMs : typeDelayMs;
    const clampedDelay = clamp(delay, 20, 1000);

    let timeout = window.setTimeout(() => {
      if (!deleting && charIndex < current.length) {
        setCharIndex((value) => value + 1);
        return;
      }
      if (!deleting && charIndex >= current.length) {
        setDeleting(true);
        return;
      }
      if (deleting && charIndex > 0) {
        setCharIndex((value) => value - 1);
        return;
      }
      if (deleting && charIndex === 0) {
        setDeleting(false);
        setPhraseIndex((value) => (value + 1) % safePhrases.length);
      }
    }, clampedDelay);

    return () => window.clearTimeout(timeout);
  }, [charIndex, deleting, deleteDelayMs, phraseIndex, safePhrases, typeDelayMs]);

  useEffect(() => {
    if (safePhrases.length === 0) return;
    const current = safePhrases[phraseIndex % safePhrases.length];
    if (!deleting && charIndex === current.length) {
      const hold = clamp(holdDelayMs, 200, 10000);
      const timeout = window.setTimeout(() => {
        setDeleting(true);
      }, hold);
      return () => window.clearTimeout(timeout);
    }
    return;
  }, [charIndex, deleting, holdDelayMs, phraseIndex, safePhrases]);

  if (safePhrases.length === 0) {
    return "";
  }
  const current = safePhrases[phraseIndex % safePhrases.length];
  return current.slice(0, charIndex);
};

export default useTypewriter;
