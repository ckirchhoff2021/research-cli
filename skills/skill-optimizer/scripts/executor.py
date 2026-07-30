import json
import argparse

import os
from common import ChatModel, ensure_optimizer_api_config


def save_cases(cases, file_path):
    """Save cases to a JSON file."""
    output_dir = os.path.dirname(os.path.abspath(file_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(cases, file, indent=2, ensure_ascii=False)


def batch_evaluate(args):
    optimizer_api = ensure_optimizer_api_config()
    model = ChatModel(
        optimizer_api["OPTIMIZER_API_URL"],
        optimizer_api["OPTIMIZER_API_KEY"],
        optimizer_api["OPTIMIZER_MODEL_NAME"],
        args.enable_thinking,
    )
    with open(args.trace_file, "r", encoding="utf-8") as file:
        traces = json.load(file)
    corrects = []
    failures = []
    for trace in traces:
        task = trace["task"]
        expected = trace["expected"]
        task_traces = trace["traces"]
        if len(task_traces) == 0:
            failures.append(trace)
            continue
        
        agent_output = task_traces[-1]
        if agent_output["type"] != "output":
            failures.append(trace)
            continue
        
        judge = ''
        
        try:
            try:
                # use responses first
                judge = model.responses(
                    f"Task:{task}\n Expected:{expected}\n Agent's output:{agent_output['content']}", 
                    system_prompt=args.system_prompt
                )
            except Exception as e:
                # use chat completion second
                print(f"responses api failed, fallback to chat_completion, err={e}")
                judge = model.chat_completion(
                    f"Task:{task}\n Expected:{expected}\n Agent's output:{agent_output['content']}", 
                    system_prompt=args.system_prompt
                )
        except Exception as outer_e:
            print(f"Both responses and chat_completion failed, err={outer_e}")
            trace["evaluation_error"] = str(outer_e)
            failures.append(trace)
            continue
        
        judge = judge.strip() if isinstance(judge, str) else ""
        if judge == "True":
            corrects.append(trace)
        elif judge == 'False':
            failures.append(trace)
        else:
            trace["evaluation_error"] = f"judge returned invalid result {judge!r}"
            failures.append(trace)
        
    total = len(corrects) + len(failures)
    accuracy = 0.0 if total == 0 else len(corrects) / total
    evaluation_failures = [
        trace for trace in failures
        if "evaluation_error" in trace
    ]
    print('Corrects number: ', len(corrects))
    print('Failures number: ', len(failures))
    print('Evaluation error number: ', len(evaluation_failures))
    # for trace in evaluation_failures[:3]:
    #     print(f"Evaluation error: task={trace['task']!r}, error={trace['evaluation_error']}")
    print(f"Accuracy: {accuracy:.4f}")
    
    if args.successes_file:
        save_cases(corrects, args.successes_file)
    
    if args.failures_file:
        save_cases(failures, args.failures_file)
        
    return accuracy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a the skill traces")
    parser.add_argument("--enable_thinking", action="store_true", help="Enable thinking in the model")
    parser.add_argument("--system_prompt", type=str, required=True, help="The system prompt to use for the model")
    parser.add_argument("--trace_file", type=str, required=True, help="The trace file to use for the model")
    parser.add_argument("--successes_file", type=str, required=False, help="The successes file to save")
    parser.add_argument("--failures_file", type=str, required=False, help="The failures file to save results")
    
    args = parser.parse_args()
    system_prompt_path = os.path.abspath(args.system_prompt)
    if os.path.isfile(system_prompt_path):
        with open(system_prompt_path, "r", encoding="utf-8") as file:
            args.system_prompt = file.read().strip()
    batch_evaluate(args)
