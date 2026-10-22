// Microphone capture via MediaRecorder, for dictation (STT).
export class Recorder {
  constructor() {
    this.recorder = null;
    this.chunks = [];
    this.stream = null;
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";
    this.recorder = mime ? new MediaRecorder(this.stream, { mimeType: mime }) : new MediaRecorder(this.stream);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => {
      if (e.data && e.data.size) this.chunks.push(e.data);
    };
    this.recorder.start();
  }

  stop() {
    return new Promise((resolve) => {
      if (!this.recorder) {
        resolve(null);
        return;
      }
      this.recorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: this.recorder.mimeType || "audio/webm" });
        this.stream.getTracks().forEach((tr) => tr.stop());
        resolve(blob);
      };
      this.recorder.stop();
    });
  }

  get active() {
    return !!this.recorder && this.recorder.state === "recording";
  }
}
