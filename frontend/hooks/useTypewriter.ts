import { useState, useEffect, useCallback } from "react";

const useTypewriter = (
  phrases: string[],
  typingSpeed = 80,
  deletingSpeed = 40,
  pauseDelay = 2000
) => {
  const [text, setText] = useState("");
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);

  const tick = useCallback(() => {
    const currentPhrase = phrases[phraseIndex];

    if (!isDeleting) {
      setText(currentPhrase.slice(0, text.length + 1));
      if (text.length + 1 === currentPhrase.length) {
        setTimeout(() => setIsDeleting(true), pauseDelay);
        return;
      }
    } else {
      setText(currentPhrase.slice(0, text.length - 1));
      if (text.length - 1 === 0) {
        setIsDeleting(false);
        setPhraseIndex((prev) => (prev + 1) % phrases.length);
        return;
      }
    }
  }, [text, phraseIndex, isDeleting, phrases, pauseDelay]);

  useEffect(() => {
    const speed = isDeleting ? deletingSpeed : typingSpeed;
    const timer = setTimeout(tick, speed);
    return () => clearTimeout(timer);
  }, [tick, isDeleting, typingSpeed, deletingSpeed]);

  return text;
};

export default useTypewriter;
