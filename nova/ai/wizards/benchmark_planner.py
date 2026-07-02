import time
import sys
import os
import gc

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.ai.planner import Planner, Goal

def run_benchmark():
    print("==================================================")
    print("      Nova Planner Optimization Benchmark")
    print("==================================================")
    
    planner = Planner()
    
    # Target Goal
    goal = Goal(description="Build a Flask website", priority="high")
    
    # 1. First run: Uncached / Cold Start
    gc.collect()
    start_time = time.perf_counter()
    result_cold = planner.create_plan(goal)
    cold_latency = (time.perf_counter() - start_time) * 1000.0 # ms
    
    assert result_cold.success, "Cold run failed!"
    assert result_cold.plan is not None
    
    print(f"Cold Start Planning Latency: {cold_latency:.3f} ms")
    print(f"Generated steps count: {len(result_cold.plan.steps)}")
    
    # 2. Subsequent runs: Cached / Hot Run
    iterations = 100
    hot_latencies = []
    
    for _ in range(iterations):
        start_time = time.perf_counter()
        result_hot = planner.create_plan(goal)
        hot_latency = (time.perf_counter() - start_time) * 1000.0 # ms
        hot_latencies.append(hot_latency)
        
        assert result_hot.success, "Hot run failed!"
        assert result_hot.plan is not None
        assert result_hot.plan.id != result_cold.plan.id, "Cache hit did not remap plan UUID!"
        
    avg_hot_latency = sum(hot_latencies) / iterations
    min_hot_latency = min(hot_latencies)
    max_hot_latency = max(hot_latencies)
    
    print(f"Average Cached Planning Latency (over {iterations} runs): {avg_hot_latency:.3f} ms")
    print(f"Min Cached Planning Latency: {min_hot_latency:.3f} ms")
    print(f"Max Cached Planning Latency: {max_hot_latency:.3f} ms")
    
    speedup = cold_latency / avg_hot_latency
    print(f"Planning Speedup factor (Cold vs Cached): {speedup:.1f}x")
    
    # 3. Merging / Deduplication verification
    # Create goal containing duplicates (e.g. two separate identical steps under same rule logic)
    print("\nVerifying Duplicate Step Optimizer:")
    # We will trigger the Flask website goal and check for step merging
    # The Flask rules have "Create Folder", "Create Virtual Environment", "Install Flask" under Setup,
    # "Generate Files" under App Development, and "Run Server" under Execution.
    # Total distinct leaf steps is 5, parents is 4. Total = 9 steps.
    # Let's verify no duplicate leaf steps exist.
    distinct_descs = {s.description for s in result_cold.plan.steps if not s.child_ids}
    print(f"Distinct leaf steps descriptions: {len(distinct_descs)} of {len([s for s in result_cold.plan.steps if not s.child_ids])}")
    
    # Let's count parallel phases
    phases = planner.get_execution_phases(result_cold.plan)
    print(f"Optimal Parallel Execution Phases: {len(phases)}")
    for i, phase in enumerate(phases):
        print(f"  Phase {i}: {len(phase)} steps can execute in parallel")
        
    print("==================================================")

if __name__ == "__main__":
    run_benchmark()
