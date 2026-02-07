import { useEffect, useRef, useState } from "react";
import Aurora from "@/components/Aurora";
import { Sparkles, ArrowRight, Paperclip, Image, Mic, X, Check } from "lucide-react";
import penguinIcon from "@/assets/penguin-icon.svg";
import useTypewriter from "@/hooks/useTypewriter";

const PLACEHOLDER_PHRASES = [
  "What do you want to talk about?",
  "Describe your idea...",
  "Paste your blog text here...",
];

const API_BASE = "http://localhost:8000";

const Index = () => {
  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [attachedPhoto, setAttachedPhoto] = useState<File | null>(null);
  const [attachedVoice, setAttachedVoice] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [logText, setLogText] = useState<string>("");
  const placeholderText = useTypewriter(PLACEHOLDER_PHRASES, 70, 35, 2200);
  const currentRunIdRef = useRef<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const voiceInputRef = useRef<HTMLInputElement>(null);

  const hasText = prompt.trim().length > 0;
  const hasInput = hasText || Boolean(attachedFile);
  const allUploaded = hasInput && attachedPhoto && attachedVoice;

  const handleGenerate = async () => {
    if (!hasInput || !attachedPhoto || !attachedVoice) return;
    setIsGenerating(true);
    setError(null);
    setVideoUrl(null);
    setLogText("");
    const runId = crypto.randomUUID();
    currentRunIdRef.current = runId;

    const formData = new FormData();
    if (attachedFile) {
      formData.append("file", attachedFile);
    } else {
      formData.append("text", prompt.trim());
    }
    formData.append("photo", attachedPhoto);
    formData.append("voice", attachedVoice);
    formData.append("run_id", runId);

    try {
      const response = await fetch(`${API_BASE}/generate`, {
        method: "POST",
        body: formData,
      });
      let payload: any = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }
      if (!response.ok) {
        setError(payload?.detail || "Generation failed. Check the API logs.");
        return;
      }
      const url = payload?.video_url;
      const responseRunId = payload?.run_id;
      if (!url) {
        setError("Video URL missing from API response.");
        return;
      }
      if (responseRunId) {
        const logsResponse = await fetch(`${API_BASE}/logs/${responseRunId}`);
        if (logsResponse.ok) {
          const logsPayload = await logsResponse.json();
          if (typeof logsPayload?.log === "string") {
            setLogText(logsPayload.log);
          }
        }
      }
      setVideoUrl(url);
    } catch (err) {
      setError("Could not reach the local API. Is it running on port 8000?");
    } finally {
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    if (!isGenerating) return;
    let active = true;
    let timer: number | undefined;

    const poll = async () => {
      try {
        if (!active) return;
        const runId = currentRunIdRef.current;
        if (!runId) {
          return;
        }
        const response = await fetch(`${API_BASE}/logs/${runId}`);
        if (response.ok) {
          const payload = await response.json();
          if (typeof payload?.log === "string") {
            setLogText(payload.log);
          }
        }
      } catch {
        // Ignore log polling errors while generating.
      } finally {
        if (active) {
          timer = window.setTimeout(poll, 2000);
        }
      }
    };

    poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [isGenerating]);

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".txt,.md,.csv"
        onChange={(e) => setAttachedFile(e.target.files?.[0] || null)}
      />
      <input
        ref={photoInputRef}
        type="file"
        className="hidden"
        accept="image/*"
        onChange={(e) => setAttachedPhoto(e.target.files?.[0] || null)}
      />
      <input
        ref={voiceInputRef}
        type="file"
        className="hidden"
        accept="audio/*"
        onChange={(e) => setAttachedVoice(e.target.files?.[0] || null)}
      />

      {/* Aurora Background */}
      <div className="absolute inset-0 z-0">
        <Aurora
          colorStops={["#7cff67", "#B19EEF", "#5227FF"]}
          blend={0.5}
          amplitude={1.0}
          speed={1}
        />
      </div>

      {/* Dark overlay for readability */}
      <div className="absolute inset-0 z-[1] bg-background/40" />

      {/* Content */}
      <div className="relative z-10 flex min-h-screen flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-4 sm:px-8 sm:py-6">
          <div className="flex items-center gap-2">
            <img src={penguinIcon} alt="Penguinz logo" className="h-7 w-7 sm:h-8 sm:w-8" />
            <h2 className="font-serif text-xl font-bold tracking-wide text-foreground sm:text-2xl">
              Penguinz
            </h2>
          </div>
        </header>

        {/* Hero Section */}
        <main className="flex flex-1 flex-col items-center justify-center px-4">
          <div className="w-full max-w-3xl text-center">
            {/* Hero Text */}
            <h1 className="mb-4 font-serif text-4xl font-bold leading-tight tracking-tight text-foreground opacity-0 animate-fade-in-up sm:text-5xl md:text-7xl">
              Turn your blogs
              <br />
              into videos
            </h1>

            <p
              className="mx-auto mb-8 max-w-lg font-serif text-base text-foreground/50 opacity-0 animate-fade-in-up sm:mb-12 sm:text-lg"
              style={{ animationDelay: "0.2s" }}
            >
              Upload your blog, upload your image, and upload your voice — we'll turn it into a great story.
            </p>

            {/* Input Area */}
            <div
              className="mx-auto w-full max-w-2xl opacity-0 animate-fade-in-up"
              style={{ animationDelay: "0.4s" }}
            >
              <div className="group relative rounded-xl border border-border/30 bg-card/60 p-1.5 shadow-2xl backdrop-blur-xl transition-all focus-within:border-primary/40 focus-within:shadow-primary/10 sm:rounded-2xl sm:p-2">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder={placeholderText}
                  rows={3}
                  className="w-full resize-none rounded-lg bg-transparent px-4 py-3 font-sans text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none sm:rounded-xl sm:px-5 sm:py-4 sm:text-sm"
                />

                {/* Upload status chips */}
                {(attachedFile || attachedPhoto || attachedVoice) && (
                  <div className="flex flex-wrap gap-1.5 px-3 pb-2 sm:gap-2 sm:px-4">
                    {attachedFile && (
                      <span className="flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] text-primary sm:px-2.5 sm:py-1 sm:text-xs">
                        <Paperclip className="h-3 w-3" />
                        <span className="max-w-[80px] truncate sm:max-w-[120px]">{attachedFile.name}</span>
                        <button onClick={() => { setAttachedFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }} className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-primary/20">
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    )}
                    {attachedPhoto && (
                      <span className="flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] text-primary sm:px-2.5 sm:py-1 sm:text-xs">
                        <Image className="h-3 w-3" />
                        <span className="max-w-[80px] truncate sm:max-w-[120px]">{attachedPhoto.name}</span>
                        <button onClick={() => { setAttachedPhoto(null); if (photoInputRef.current) photoInputRef.current.value = ""; }} className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-primary/20">
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    )}
                    {attachedVoice && (
                      <span className="flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] text-primary sm:px-2.5 sm:py-1 sm:text-xs">
                        <Mic className="h-3 w-3" />
                        <span className="max-w-[80px] truncate sm:max-w-[120px]">{attachedVoice.name}</span>
                        <button onClick={() => { setAttachedVoice(null); if (voiceInputRef.current) voiceInputRef.current.value = ""; }} className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-primary/20">
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-between px-2 pb-1.5 sm:px-3 sm:pb-2">
                  <div className="flex items-center gap-1 text-muted-foreground sm:gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className={`rounded-lg p-1.5 transition-colors hover:bg-muted/30 hover:text-foreground ${attachedFile ? "text-primary" : ""}`}
                      aria-label="Upload file"
                    >
                      {attachedFile ? <Check className="h-4 w-4" /> : <Paperclip className="h-4 w-4" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => photoInputRef.current?.click()}
                      className={`rounded-lg p-1.5 transition-colors hover:bg-muted/30 hover:text-foreground ${attachedPhoto ? "text-primary" : ""}`}
                      aria-label="Upload photo"
                    >
                      {attachedPhoto ? <Check className="h-4 w-4" /> : <Image className="h-4 w-4" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => voiceInputRef.current?.click()}
                      className={`rounded-lg p-1.5 transition-colors hover:bg-muted/30 hover:text-foreground ${attachedVoice ? "text-primary" : ""}`}
                      aria-label="Upload voice"
                    >
                      {attachedVoice ? <Check className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                    </button>
                    <span className="hidden text-xs sm:inline">
                      {prompt.length > 0
                        ? `${prompt.length} characters`
                        : allUploaded
                        ? "All inputs attached ✓"
                        : "Add text or a file + photo + voice"}
                    </span>
                  </div>
                  <button
                    onClick={handleGenerate}
                    disabled={!hasInput || !allUploaded || isGenerating}
                    className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 font-sans text-xs font-medium text-primary-foreground transition-all hover:brightness-110 disabled:opacity-40 disabled:hover:brightness-100 sm:gap-2 sm:rounded-xl sm:px-6 sm:py-2.5 sm:text-sm"
                  >
                    {isGenerating ? (
                      <>
                        <Sparkles className="h-3.5 w-3.5 animate-spin sm:h-4 sm:w-4" />
                        <span className="hidden sm:inline">Generating...</span>
                        <span className="sm:hidden">...</span>
                      </>
                    ) : (
                      <>
                        Generate
                        <ArrowRight className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Feature Pills */}
            <div
              className="mt-6 flex flex-wrap items-center justify-center gap-2 opacity-0 animate-fade-in-up sm:mt-8 sm:gap-3"
              style={{ animationDelay: "0.6s" }}
            >
              {["Auto captions", "AI voices", "Stock footage", "Custom styles"].map(
                (feature) => (
                  <span
                    key={feature}
                    className="rounded-full border border-border/30 bg-muted/20 px-3 py-1 font-sans text-[10px] text-foreground/60 backdrop-blur-sm sm:px-4 sm:py-1.5 sm:text-xs"
                  >
                    {feature}
                  </span>
                )
              )}
            </div>

            {error && (
              <div className="mt-6 text-sm text-red-200/90">
                {error}
              </div>
            )}

            {(isGenerating || logText) && (
              <div className="mt-6 w-full max-w-3xl rounded-xl border border-border/30 bg-card/60 p-4 text-left text-xs text-foreground/80">
                <div className="mb-2 font-semibold text-foreground">Pipeline logs</div>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap">
                  {logText || "Running..."}
                </pre>
              </div>
            )}

            {videoUrl && (
              <div className="mt-6 w-full max-w-3xl">
                <video
                  className="w-full rounded-xl border border-border/30 shadow-lg"
                  controls
                  src={videoUrl}
                />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Index;