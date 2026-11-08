"""Greedy generation with the fine-tuned Pythia-70M student (used by the service and by
training/predict.py, so evaluation and serving produce identical text)."""
import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

from prompting import extract_output, format_prompt


class _StopOnNewline(StoppingCriteria):
    def __init__(self, tokenizer, prompt_len):
        self.tokenizer = tokenizer
        self.prompt_len = prompt_len

    def __call__(self, input_ids, scores, **kwargs):
        new = input_ids[0, self.prompt_len:]
        return len(new) > 0 and "\n" in self.tokenizer.decode(new[-1:])


class ParserModel:
    def __init__(self, model_dir, max_new_tokens=48, num_threads=None, revision=None):
        threads = num_threads or int(os.environ.get("TORCH_NUM_THREADS", "0")) or None
        if threads:
            torch.set_num_threads(threads)
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, revision=revision)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, revision=revision, torch_dtype=torch.float32
        )
        self.model.eval()
        self.max_new_tokens = int(max_new_tokens)
        self.eos = self.tokenizer.eos_token_id

    @torch.inference_mode()
    def generate_raw(self, text):
        """Return (prompt-free generated text, extracted answer)."""
        enc = self.tokenizer(format_prompt(text), return_tensors="pt")
        prompt_len = enc["input_ids"].shape[1]
        out = self.model.generate(
            **enc,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            num_beams=1,
            eos_token_id=self.eos,
            pad_token_id=self.eos,
            stopping_criteria=StoppingCriteriaList([_StopOnNewline(self.tokenizer, prompt_len)]),
        )
        generated = self.tokenizer.decode(out[0, prompt_len:], skip_special_tokens=True)
        return generated, extract_output(generated)

    def parse(self, text):
        return self.generate_raw(text)[1]
