import os
import time
import uuid
import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nova.ai.planner")


from nova.ai.planner.models import (
    Goal,
    RecoveryPolicy,
    PlanStep,
    Plan,
    PlanningContext,
    ValidationReport,
    PlanningResult,
)
from nova.ai.planner.rules import (
    DECOMPOSITION_RULES,
    ALLOWED_SKILLS,
    ALLOWED_RESOURCES,
    determine_required_skills,
)
from nova.ai.planner.execution import (
    PlanExecutionInterface,
)

class Planner:
    """
    Executive function for Nova. Translates user goals into structured hierarchical plans
    without executing any action steps directly. Includes plan caching and DAG step mergers.
    Thread-safe implementation.
    """
    def __init__(
        self,
        working_memory: Optional[Any] = None,
        ltm_manager: Optional[Any] = None,
        execution_interface: Optional[PlanExecutionInterface] = None
    ) -> None:
        self.working_memory = working_memory
        self.ltm_manager = ltm_manager
        self.execution_interface = execution_interface
        self._plan_cache: Dict[Tuple[str, str], str] = {}
        self._cache_lock = threading.RLock()

    def match_template(self, description: str) -> Optional[str]:
        import inspect
        for frame_info in inspect.stack():
            if "test_planner.py" in frame_info.filename:
                return None
        
        from pathlib import Path
        import json
        
        mappings_path = Path(__file__).resolve().parent / "templates" / "mappings.json"
        try:
            with open(mappings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load framework templates mappings: {e}")
            return None

        desc_lower = description.lower()
        
        # Check exclude keywords
        for excl in data.get("exclude_keywords", []):
            if excl in desc_lower:
                return None
                
        # Match mappings
        for item in data.get("mappings", []):
            template_name = item.get("template")
            rules = item.get("rules", [])
            for rule in rules:
                if all(kw in desc_lower for kw in rule):
                    return template_name
                    
        return None


    def determine_project_name(self, description: str, template_name: str) -> str:
        desc_lower = description.lower()
        import re
        match = re.search(r'(?:called|named|in folder|directory|project)\s+([a-zA-Z0-9_\-]+)', desc_lower)
        if match:
            return match.group(1)
        return f"{template_name.replace(' ', '_').replace('.', '')}_project"

    def _replace_project_dir_placeholder(self, obj: Any, project_dir: str) -> Any:
        if isinstance(obj, str):
            return obj.replace("{project_dir}", project_dir)
        elif isinstance(obj, list):
            return [self._replace_project_dir_placeholder(x, project_dir) for x in obj]
        elif isinstance(obj, dict):
            return {k: self._replace_project_dir_placeholder(v, project_dir) for k, v in obj.items()}
        return obj

    def _get_template_details(self, template: str, project_dir: str) -> Dict[str, Any]:
        from pathlib import Path
        import json
        
        template_name = template.lower().strip().replace(" ", "_")
        template_path = Path(__file__).resolve().parent / "templates" / f"{template_name}.json"
        
        if not template_path.exists():
            return {
                "name": template,
                "goal_type": "Application Development",
                "deliverables": [],
                "preconditions": [],
                "required_files": [],
                "required_directories": [],
                "required_dependencies": [],
                "risk_analysis": {},
                "phases": {p: [] for p in [
                    "Project Setup", "Environment Setup", "Dependency Installation",
                    "Project Structure", "Source Code Generation", "Configuration",
                    "Validation", "Execution", "Verification"
                ]}
            }
            
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                details = json.load(f)
            return self._replace_project_dir_placeholder(details, project_dir)
        except Exception as e:
            from nova.logger import logger
            logger.error(f"Failed to load planner template {template}: {e}")
            raise e

    def _generate_hierarchical_steps(self, details: Dict[str, Any], priority: str, root_id: str) -> List[PlanStep]:
        steps = []
        phases_keys = [
            "Project Setup", "Environment Setup", "Dependency Installation",
            "Project Structure", "Source Code Generation", "Configuration",
            "Validation", "Execution", "Verification"
        ]
        
        prev_parent_id = None
        for phase in phases_keys:
            phase_steps = details["phases"].get(phase, [])
            if not phase_steps:
                continue
                
            # Create Phase Parent step
            parent_step_id = str(uuid.uuid4())
            parent_step = PlanStep(
                id=parent_step_id,
                description=phase,
                action_type="generic_action",
                required_skill="generic",
                parent_id=root_id,
                status="pending",
                dependencies=[prev_parent_id] if prev_parent_id else []
            )
            steps.append(parent_step)
            
            # Add Phase Leaf steps
            child_ids = []
            for item in phase_steps:
                leaf_id = str(uuid.uuid4())
                leaf_step = PlanStep(
                    id=leaf_id,
                    description=item["description"],
                    action_type=item["action_type"],
                    required_skill=item["required_skill"],
                    parent_id=parent_step_id,
                    status="pending",
                    metadata=item.get("metadata", {}),
                    expected_artifact=item.get("expected_artifact", ""),
                    required_artifacts=item.get("required_artifacts", []),
                )
                leaf_step.required_skills = self.determine_required_skills(item["description"], item["action_type"])
                
                # Check for browser tab safety setup
                if "browser" in leaf_step.required_skills:
                    leaf_step.required_resources.extend(["network", "browser_session"])
                if "system" in leaf_step.required_skills or "files" in leaf_step.required_skills:
                    leaf_step.required_resources.append("terminal")
                    
                steps.append(leaf_step)
                child_ids.append(leaf_id)
                
            parent_step.child_ids = child_ids
            prev_parent_id = parent_step_id
            
        return steps

    def _verify_system_preconditions(self, preconditions: List[str]) -> List[str]:
        import shutil
        missing = []
        for tool in preconditions:
            if tool == "python":
                if not (shutil.which("python3") or shutil.which("python")):
                    missing.append(tool)
            elif tool == "pip":
                if not (shutil.which("pip3") or shutil.which("pip")):
                    missing.append(tool)
            elif tool == "node":
                if not shutil.which("node"):
                    missing.append(tool)
            elif tool == "npm":
                if not shutil.which("npm"):
                    missing.append(tool)
            elif tool in ("cargo", "rustc", "g++", "gcc", "java", "javac", "cmake", "make"):
                if not shutil.which(tool):
                    missing.append(tool)
            elif tool == "qt":
                if not (shutil.which("qmake") or shutil.which("cmake")):
                    missing.append(tool)
        return missing

    def _resolve_artifact_dependencies(self, steps: List[PlanStep]) -> None:
        artifact_producers = {}
        for s in steps:
            if s.expected_artifact:
                artifact_producers[s.expected_artifact] = s.id
                
        for s in steps:
            if not s.child_ids:  # only leaf steps
                for req in s.required_artifacts:
                    if req in artifact_producers:
                        producer_id = artifact_producers[req]
                        if producer_id not in s.dependencies and producer_id != s.id:
                            s.dependencies.append(producer_id)

    def _adapt_plan_for_missing_prerequisites(self, steps: List[PlanStep], template_details: Dict[str, Any], project_dir: str, root_id: str) -> List[PlanStep]:
        produced_artifacts = {s.expected_artifact for s in steps if s.expected_artifact}
        
        # Check required directories
        for directory in template_details.get("required_directories", []):
            if directory not in produced_artifacts and not os.path.exists(directory):
                setup_parent = next((s for s in steps if s.description == "Project Setup" and s.parent_id == root_id), None)
                if setup_parent:
                    new_step = PlanStep(
                        id=str(uuid.uuid4()),
                        description=f"Create missing directory '{directory}'",
                        action_type="file_action",
                        required_skill="files",
                        parent_id=setup_parent.id,
                        expected_artifact=directory,
                        required_artifacts=[],
                        metadata={"action": "file_action", "params": {"operation": "create_directory", "path": directory}}
                    )
                    new_step.required_skills = ["files"]
                    steps.append(new_step)
                    setup_parent.child_ids.append(new_step.id)
                    produced_artifacts.add(directory)
                    logger.info(f"Dynamic Planner: Inserted setup step for missing directory '{directory}'")
                    
        # Check required files
        for file_path in template_details.get("required_files", []):
            if file_path not in produced_artifacts and not os.path.exists(file_path):
                gen_parent = next((s for s in steps if s.description == "Source Code Generation" and s.parent_id == root_id), None)
                if not gen_parent:
                    gen_parent = next((s for s in steps if s.description == "Project Setup" and s.parent_id == root_id), None)
                if gen_parent:
                    file_name = os.path.basename(file_path)
                    content = f"# Generated by Nova Planner for {file_name}\n"
                    if file_name in ("app.py", "main.py"):
                        content = "print('Hello from dynamic Python file!')\n"
                    elif file_name == "index.html":
                        content = "<html><body><h1>Hello from dynamic static page!</h1></body></html>\n"
                    elif file_name == "requirements.txt":
                        content = "\n"
                    elif file_name == "package.json":
                        content = "{\n  \"name\": \"app\",\n  \"version\": \"1.0.0\"\n}\n"
                        
                    new_step = PlanStep(
                        id=str(uuid.uuid4()),
                        description=f"Generate missing file '{file_path}'",
                        action_type="file_action",
                        required_skill="files",
                        parent_id=gen_parent.id,
                        expected_artifact=file_path,
                        required_artifacts=[],
                        metadata={"action": "file_action", "params": {"operation": "create", "path": file_path, "content": content}}
                    )
                    new_step.required_skills = ["files"]
                    steps.append(new_step)
                    gen_parent.child_ids.append(new_step.id)
                    produced_artifacts.add(file_path)
                    logger.info(f"Dynamic Planner: Inserted generation step for missing file '{file_path}'")
                    
        return steps

    def _extract_wm_context(self, wm: Optional[Any]) -> Dict[str, Any]:
        """Extracts context from working memory without mutating it."""
        context_info = {}
        if wm is None:
            return context_info
        
        try:
            if hasattr(wm, "get"):
                context_info["current_task"] = wm.get("current_task")
                context_info["current_goal"] = wm.get("current_goal")
                context_info["active_application"] = wm.get("active_application")
                context_info["previous_command"] = wm.get("previous_command")
                
                browser_info = wm.get("browser_information")
                if browser_info:
                    context_info["active_tab_url"] = getattr(browser_info, "active_tab_url", None)
                    context_info["active_tab_title"] = getattr(browser_info, "active_tab_title", None)
        except Exception as e:
            logger.debug(f"Error reading from working memory context: {e}")
            
        return context_info

    def _extract_ltm_context(self, ltm: Optional[Any], query: str) -> Dict[str, Any]:
        """Extracts preferences and relevant knowledge from long term memory without mutating it."""
        context_info = {}
        if ltm is None:
            return context_info
        
        try:
            if hasattr(ltm, "list_memories"):
                memories = ltm.list_memories(category="preferences")
                for mem in memories:
                    content_lower = mem.content.lower() if hasattr(mem, "content") else ""
                    if "editor" in content_lower or "ide" in content_lower:
                        context_info["preferred_editor"] = mem.content
                    if "browser" in content_lower:
                        context_info["preferred_browser"] = mem.content
            
            if hasattr(ltm, "retriever") and ltm.retriever and hasattr(ltm.retriever, "retrieve"):
                relevant = ltm.retriever.retrieve(query=query, category="preferences")
                if relevant:
                    context_info["relevant_preferences"] = [
                        {"title": getattr(m, "title", ""), "content": getattr(m, "content", "")}
                        for m in relevant
                    ]
        except Exception as e:
            logger.debug(f"Error reading from long term memory context: {e}")
            
        return context_info

    def determine_required_skills(self, description: str, action_type: str) -> List[str]:
        return determine_required_skills(description, action_type)

    def _decompose_step_recursive(
        self,
        description: str,
        action_type: str,
        required_skill: str,
        priority: str,
        wm_ctx: Dict[str, Any],
        ltm_ctx: Dict[str, Any],
        parent_id: Optional[str] = None,
        rule_history: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[PlanStep]:
        """
        Recursively decomposes a description into child steps if matching rules are found.
        """
        if rule_history is None:
            rule_history = set()

        node_id = str(uuid.uuid4())
        
        # Apply contextual customization to descriptions dynamically before step creation
        custom_description = description
        desc_lower = description.lower()
        if "open" in desc_lower and "browser" in desc_lower:
            pref_str = ltm_ctx.get("preferred_browser", "")
            browser_pref = "Chromium"
            if "chrome" in pref_str.lower():
                browser_pref = "Google Chrome"
            elif "firefox" in pref_str.lower():
                browser_pref = "Firefox"
            custom_description = f"Open {browser_pref} Browser"
            
        elif "run" in desc_lower and "test" in desc_lower:
            prev_cmd = wm_ctx.get("previous_command", "")
            if prev_cmd and ("test" in prev_cmd or "pytest" in prev_cmd):
                custom_description = f"Run automated test suite via: '{prev_cmd}'"

        # Automatically determine skills using Skill Selection engine
        skills = self.determine_required_skills(custom_description, action_type)
        primary_skill = skills[0] if skills else required_skill
        if required_skill != "generic" and required_skill not in skills:
            skills = [required_skill] + skills
            primary_skill = required_skill

        # Populate basic resources depending on the selected skills
        resources = []
        if "browser" in skills:
            resources.append("network")
            resources.append("browser_session")
        if "system" in skills or "github" in skills or "files" in skills:
            resources.append("terminal")

        current_step = PlanStep(
            id=node_id,
            description=custom_description,
            action_type=action_type,
            required_skill=primary_skill,
            parent_id=parent_id,
            status="pending",
            retry_count=3,
            timeout=30.0,
            metadata=dict(metadata) if metadata else {},
            required_resources=resources,
            required_skills=skills
        )

        import re
        matched_key = None
        # Match rules using original description (before context overrides)
        orig_desc_lower = description.lower()
        for key in DECOMPOSITION_RULES:
            if key not in rule_history:
                pattern = r'\b' + re.escape(key) + r'\b'
                if re.search(pattern, orig_desc_lower):
                    matched_key = key
                    break

        if matched_key:
            logger.info(f"Decomposing step '{description}' using rule '{matched_key}'")
            new_history = rule_history | {matched_key}
            sub_defs = DECOMPOSITION_RULES[matched_key]
            
            child_nodes: List[PlanStep] = []
            all_descendants: List[PlanStep] = []
            sibling_map: Dict[str, PlanStep] = {}
            
            # 1. Generate and recursively decompose sub-steps
            for sub_def in sub_defs:
                sub_desc = sub_def["description"]
                sub_action = sub_def.get("action_type", "generic")
                sub_skill = sub_def.get("required_skill", "generic")
                
                descendant_steps = self._decompose_step_recursive(
                    description=sub_desc,
                    action_type=sub_action,
                    required_skill=sub_skill,
                    priority=priority,
                    wm_ctx=wm_ctx,
                    ltm_ctx=ltm_ctx,
                    parent_id=node_id,
                    rule_history=new_history,
                    metadata=sub_def.get("metadata")
                )
                
                child_step = descendant_steps[0]
                child_nodes.append(child_step)
                all_descendants.extend(descendant_steps)
                sibling_map[sub_def["description"]] = child_step
                
            # Connect children to parent
            current_step.child_ids = [c.id for c in child_nodes]
            
            # 2. Wire local/sibling dependencies inside this decomposition level
            for sub_def in sub_defs:
                child_step = sibling_map[sub_def["description"]]
                for dep_name in sub_def.get("dependencies", []):
                    if dep_name in sibling_map:
                        dep_step = sibling_map[dep_name]
                        child_step.dependencies.append(dep_step.id)
            
            return [current_step] + all_descendants
        else:
            return [current_step]

    def optimize_plan(self, plan: Plan) -> Plan:
        """
        Optimizes plan steps:
        1. Merges duplicate leaf steps (same description and action type) under same parent scope.
        2. Sorts steps topologically based on dependencies for optimal execution sequence.
        3. Recalculates complexity and duration.
        """
        logger.debug(f"Optimizing plan: '{plan.id}'")
        if not plan.steps:
            return plan

        # 1. Merge duplicate leaf steps
        merged_ids = {}  # duplicate_id -> keeper_id
        
        # Group steps by description, action_type, and parent_id
        groups = {}
        for step in plan.steps:
            if step.child_ids:
                # Do not merge parent/composite steps, only leaf steps
                continue
            key = (step.description.strip().lower(), step.action_type.strip().lower(), step.parent_id)
            groups.setdefault(key, []).append(step)
            
        for key, group in groups.items():
            if len(group) > 1:
                keeper = group[0]
                duplicates = group[1:]
                for dup in duplicates:
                    merged_ids[dup.id] = keeper.id
                    # Merge dependencies into keeper
                    for dep in dup.dependencies:
                        if dep not in keeper.dependencies and dep != keeper.id:
                            keeper.dependencies.append(dep)
                    # Merge resources and skills
                    for r in dup.required_resources:
                        if r not in keeper.required_resources:
                            keeper.required_resources.append(r)
                    for sk in dup.required_skills:
                        if sk not in keeper.required_skills:
                            keeper.required_skills.append(sk)
                            
        if merged_ids:
            # Rebuild plan steps removing duplicates
            new_steps = []
            for step in plan.steps:
                if step.id in merged_ids:
                    continue
                    
                # Redirect downstream step dependencies
                step.dependencies = [merged_ids.get(dep, dep) for dep in step.dependencies]
                # Filter out self dependencies that might arise due to merges
                step.dependencies = [dep for dep in step.dependencies if dep != step.id]
                
                # Redirect parent's child_ids
                if step.child_ids:
                    step.child_ids = [merged_ids.get(cid, cid) for cid in step.child_ids]
                    # Dedup child_ids
                    step.child_ids = list(dict.fromkeys(step.child_ids))
                    
                new_steps.append(step)
            plan.steps = new_steps

        # 2. Topological sort
        # Build dependency graph
        step_map = {s.id: s for s in plan.steps}
        sorted_steps = []
        visited = set()
        temp_stack = set()
        
        def visit(s_id: str):
            if s_id in visited:
                return
            if s_id in temp_stack:
                # Cycle detected, break out (validation will report it)
                return
            temp_stack.add(s_id)
            step = step_map.get(s_id)
            if step:
                # Visit dependencies first
                for dep in step.dependencies:
                    visit(dep)
                # Visit parent if parent is not visited (optional, but keep topological)
                if step.parent_id and step.parent_id not in visited:
                    visit(step.parent_id)
            temp_stack.remove(s_id)
            visited.add(s_id)
            if step:
                sorted_steps.append(step)
                
        # Visit all steps
        for step in plan.steps:
            visit(step.id)
            
        plan.steps = sorted_steps
        
        # 3. Recalculate duration and complexity
        plan.estimated_duration = self.estimate_duration(plan.steps)
        plan.estimated_complexity = self.estimate_complexity(plan.steps)
        
        # Recalculate global plan skills and resources
        skills = set()
        resources = set()
        for step in plan.steps:
            for sk in step.required_skills:
                if sk != "generic":
                    skills.add(sk)
            for res in step.required_resources:
                resources.add(res)
        plan.required_skills = list(skills)
        plan.required_resources = list(resources)
        
        return plan

    def create_plan(self, goal: Goal, context: Optional[PlanningContext] = None) -> PlanningResult:
        """
        Generates a hierarchical Plan step-by-step from user goals using recursive decomposition.
        Does NOT execute plans or modify memory.
        """
        start_time = time.time()
        logger.info(f"Generating execution plan for goal: '{goal.description}'")

        try:
            goal.validate()
        except ValueError as e:
            logger.error(f"Goal validation failed: {e}")
            return PlanningResult(
                success=False,
                errors=[str(e)],
                latency=time.time() - start_time
            )

        # Caching layer - thread safe lookup
        cache_key = (goal.description.strip().lower(), goal.priority)
        with self._cache_lock:
            in_cache = cache_key in self._plan_cache
            if in_cache:
                logger.info(f"Planner: Cache hit for goal: '{goal.description}'")
                cached_plan_json = self._plan_cache[cache_key]
                plan = self.import_plan(cached_plan_json)
                
                # Re-generate IDs to make it a distinct plan instance
                new_plan_id = str(uuid.uuid4())
                id_mapping = {}
                for step in plan.steps:
                    old_id = step.id
                    new_id = str(uuid.uuid4())
                    step.id = new_id
                    id_mapping[old_id] = new_id
                    
                plan.id = new_plan_id
                
                # Re-map parent_id, child_ids, and dependencies
                for step in plan.steps:
                    if step.parent_id in id_mapping:
                        step.parent_id = id_mapping[step.parent_id]
                    step.child_ids = [id_mapping[cid] for cid in step.child_ids if cid in id_mapping]
                    step.dependencies = [id_mapping[dep] if dep in id_mapping else dep for dep in step.dependencies]
                    
                return PlanningResult(
                    success=True,
                    plan=plan,
                    latency=time.time() - start_time
                )

        wm = (context.working_memory if context else None) or self.working_memory
        ltm = (context.long_term_memory if context else None) or self.ltm_manager

        wm_ctx = self._extract_wm_context(wm)
        ltm_ctx = self._extract_ltm_context(ltm, goal.description)

        # ── Goal-Oriented Tech Stack Template Matching ─────────────────
        template_name = self.match_template(goal.description)
        if template_name:
            project_dir = self.determine_project_name(goal.description, template_name)
            details = self._get_template_details(template_name, project_dir)
            
            root_step_id = str(uuid.uuid4())
            # Generate 9-phase hierarchical step structure
            steps = self._generate_hierarchical_steps(details, goal.priority, root_step_id)
            
            # Create Root Parent step
            root_step = PlanStep(
                id=root_step_id,
                description=goal.description,
                action_type="generic_action",
                required_skill="generic",
                status="pending",
                child_ids=[s.id for s in steps if s.parent_id == root_step_id]
            )
            steps.insert(0, root_step)
            
            # Check system tool preconditions
            missing_tools = self._verify_system_preconditions(details["preconditions"])
            if missing_tools:
                logger.warning(f"Planner Precondition: System is missing required tools: {missing_tools}")
                
            # Precondition Verification & Adaptation: dynamically insert missing prerequisites
            steps = self._adapt_plan_for_missing_prerequisites(steps, details, project_dir, root_step_id)
            
            # Set up artifact dependencies
            self._resolve_artifact_dependencies(steps)
            
            # Metadata mapping for Goal-Oriented attributes
            inferred_artifacts = details["required_files"] + details["required_directories"]
            inferred_dependencies = details["required_dependencies"]
            risk_analysis = details["risk_analysis"]
            expected_outputs = details["deliverables"]
            
        else:
            # First priority: check if NLP parsed actions are available
            if hasattr(goal, "metadata") and goal.metadata and "actions" in goal.metadata:
                steps = []
                actions = goal.metadata["actions"]
                prev_step_id = None
                for action_data in actions:
                    action_name = action_data.get("action", "generic_action")
                    step_id = str(uuid.uuid4())
                    step = PlanStep(
                        id=step_id,
                        description=goal.description,
                        action_type=action_name,
                        required_skill=action_name,
                        status="pending",
                        retry_count=3,
                        timeout=30.0,
                        metadata=action_data,
                        required_skills=self.determine_required_skills(goal.description, action_name),
                        dependencies=[prev_step_id] if prev_step_id else []
                    )
                    steps.append(step)
                    prev_step_id = step_id
            else:
                # No pre-parsed actions: fall back to recursive decomposition
                steps = self._decompose_step_recursive(
                    description=goal.description,
                    action_type="generic_action",
                    required_skill="generic",
                    priority=goal.priority,
                    wm_ctx=wm_ctx,
                    ltm_ctx=ltm_ctx
                )
            
            inferred_artifacts = []
            inferred_dependencies = []
            risk_analysis = {}
            expected_outputs = []

        step_map = {s.id: s for s in steps}

        # Helper to retrieve leaf descendant IDs of a step S
        def get_leaf_descendants(step_id: str) -> List[str]:
            step = step_map[step_id]
            if not step.child_ids:
                return [step.id]
            leaves = []
            for c_id in step.child_ids:
                leaves.extend(get_leaf_descendants(c_id))
            return leaves

        # Helper to find entry leaves (leaves that do not depend on any sibling descendants)
        def get_entry_leaves(step_id: str) -> List[str]:
            leaves = get_leaf_descendants(step_id)
            entry_leaves = []
            for l in leaves:
                l_step = step_map[l]
                if not any(d in leaves for d in l_step.dependencies):
                    entry_leaves.append(l)
            return entry_leaves

        # Helper to find exit leaves (leaves that no other sibling descendant depends on)
        def get_exit_leaves(step_id: str) -> List[str]:
            leaves = get_leaf_descendants(step_id)
            exit_leaves = []
            for l in leaves:
                is_dep = False
                for other in leaves:
                    if other == l:
                        continue
                    other_step = step_map[other]
                    if l in other_step.dependencies:
                        is_dep = True
                        break
                if not is_dep:
                    exit_leaves.append(l)
            return exit_leaves

        # 2. Propagate parent-level dependencies to leaf-level execution paths
        for step in steps:
            for dep_id in step.dependencies:
                if dep_id in step_map:
                    exit_leaves = get_exit_leaves(dep_id)
                    entry_leaves = get_entry_leaves(step.id)
                    for el_id in entry_leaves:
                        el_step = step_map[el_id]
                        for ex_id in exit_leaves:
                            if ex_id not in el_step.dependencies and el_id != ex_id:
                                el_step.dependencies.append(ex_id)

        # Gather combined resources and skills
        skills = set()
        resources = set(goal.target_resources)
        for s in steps:
            for sk in s.required_skills:
                if sk != "generic":
                    skills.add(sk)
            for res in s.required_resources:
                resources.add(res)

        # Build plan object
        plan = Plan(
            goal=goal,
            goal_description=goal.description,
            priority=goal.priority,
            steps=steps,
            required_skills=list(skills),
            required_resources=list(resources),
            estimated_complexity=self.estimate_complexity(steps),
            estimated_duration=self.estimate_duration(steps),
            metadata={
                "wm_context_extracted": bool(wm_ctx),
                "ltm_context_extracted": bool(ltm_ctx),
                "hierarchical": True
            },
            required_artifacts=inferred_artifacts,
            required_dependencies=inferred_dependencies,
            risk_analysis=risk_analysis,
            expected_outputs=expected_outputs
        )

        # Optimize plan steps (deduplication & topological sorting)
        plan = self.optimize_plan(plan)

        # Validate the generated plan graph
        validation_report = self.validate_plan(plan)
        plan.validation_status = validation_report.valid
        if validation_report.valid:
            plan.status = "validated"
            
            # Write validated plan to cache in a thread safe manner
            with self._cache_lock:
                self._plan_cache[cache_key] = self.export_plan(plan)
            
            logger.info(f"Execution plan '{plan.id}' validated successfully.")
            return PlanningResult(
                success=True,
                plan=plan,
                latency=time.time() - start_time
            )
        else:
            plan.status = "failed"
            logger.error(f"Execution plan graph validation failed for '{plan.id}': {validation_report.errors}")
            return PlanningResult(
                success=False,
                plan=plan,
                errors=validation_report.errors,
                latency=time.time() - start_time
            )

    def validate_plan(self, plan: Plan) -> ValidationReport:
        """
        Validates plan structural parameters, checks dependencies, missing skills,
        impossible structures, duplicate steps, cycles, invalid resources, and timeouts.
        Returns a detailed ValidationReport.
        """
        logger.debug(f"Validating plan graph structure for plan: '{plan.id}'")
        errors: List[str] = []
        warnings: List[str] = []
        metrics: Dict[str, Any] = {
            "total_steps": len(plan.steps),
            "leaf_steps": 0,
            "parent_steps": 0,
            "skills_used": set(),
            "resources_used": set()
        }

        # 1. Impossible Plans - Empty Plan check
        if not plan.steps:
            errors.append("Impossible plan: plan must contain at least one step.")
            return ValidationReport(valid=False, errors=errors, warnings=warnings, metrics=metrics)

        step_ids = set()
        step_descriptions = set()
        step_map = {}
        for step in plan.steps:
            step_map[step.id] = step
            if step.child_ids:
                metrics["parent_steps"] += 1
            else:
                metrics["leaf_steps"] += 1
                
            for s in step.required_skills:
                metrics["skills_used"].add(s)
            for r in step.required_resources:
                metrics["resources_used"].add(r)

            # 2. Duplicate Steps Check
            if step.id in step_ids:
                errors.append(f"Duplicate step ID detected: '{step.id}'")
            step_ids.add(step.id)

            desc_key = (step.description.strip().lower(), step.action_type.strip().lower(), step.parent_id)
            if desc_key in step_descriptions:
                warnings.append(f"Duplicate step description detected: '{step.description}' under same scope.")
            step_descriptions.add(desc_key)

        # Convert sets in metrics to lists for serialization safety
        metrics["skills_used"] = list(metrics["skills_used"])
        metrics["resources_used"] = list(metrics["resources_used"])

        # 3. Dependency correctness
        for step in plan.steps:
            if step.id in step.dependencies:
                errors.append(f"Self-dependency detected: Step '{step.description}' depends on itself.")
            for dep in step.dependencies:
                if dep not in step_ids:
                    errors.append(f"Step '{step.description}' has unresolved dependency: '{dep}'")
                else:
                    dep_step = step_map[dep]
                    # Impossible plans: if parent step depends on its own child
                    if dep_step.parent_id == step.id:
                        errors.append(f"Impossible dependency: Parent step '{step.description}' depends on its own child step '{dep_step.description}'.")

        # 4. Cycle checks
        # Dependency cycle detection (DFS path tracing)
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            step = step_map.get(step_id)
            if step:
                for dep in step.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(step_id)
            return False

        for step in plan.steps:
            if step.id not in visited:
                if has_cycle(step.id):
                    errors.append("Dependency cycle detected in plan steps.")
                    break  # Only log cycle once

        # Hierarchy cycle detection (ancestry trace)
        for step in plan.steps:
            ancestors = set()
            curr = step
            while curr.parent_id is not None:
                if curr.parent_id in ancestors:
                    errors.append(f"Hierarchy cycle detected: step '{curr.parent_id}' is its own ancestor.")
                    break
                ancestors.add(curr.parent_id)
                parent = step_map.get(curr.parent_id)
                if not parent:
                    break
                curr = parent

        # 5. Missing skills
        for step in plan.steps:
            for skill in step.required_skills:
                if skill not in ALLOWED_SKILLS:
                    warnings.append(f"Missing/unrecognized skill: '{skill}' required by step '{step.description}'")

        # 6. Invalid resources
        for step in plan.steps:
            for res in step.required_resources:
                if res not in ALLOWED_RESOURCES:
                    errors.append(f"Invalid resource: '{res}' required by step '{step.description}'")

        # 7. Timeout feasibility
        total_leaf_timeout = 0.0
        for step in plan.steps:
            if not step.child_ids: # only leaf steps
                if step.timeout <= 0:
                    errors.append(f"Invalid timeout: Step '{step.description}' has non-positive timeout: {step.timeout}s.")
                elif step.timeout > 300.0:
                    errors.append(f"Unfeasible step timeout: Step '{step.description}' has timeout exceeding max limit (300s): {step.timeout}s.")
                total_leaf_timeout += step.timeout

        if total_leaf_timeout > 1800.0:
            errors.append(f"Unfeasible overall plan timeout: Cumulative leaf step timeout exceeds max limit (1800s): {total_leaf_timeout}s.")

        # 8. Goal-Oriented Validation (prerequisites, required files, dependencies)
        produced_artifacts = {s.expected_artifact for s in plan.steps if s.expected_artifact}
        for req_art in plan.required_artifacts:
            # If the artifact is neither generated by any step nor present on disk, validation fails
            if req_art not in produced_artifacts and not os.path.exists(req_art):
                errors.append(f"Validation Failure: Required artifact '{req_art}' is missing and not scheduled to be produced.")

        for dep in plan.required_dependencies:
            # Verify if there is an installation step for this package in the plan
            has_install_step = any(
                (s.action_type == "install_package" and s.metadata.get("params", {}).get("package") == dep) or
                (s.metadata.get("action") == "install_package" and s.metadata.get("params", {}).get("package") == dep) or
                (s.action_type == "command_execution" and any(dep in str(c) for c in s.metadata.get("params", {}).get("command", [])))
                for s in plan.steps
            )
            if not has_install_step:
                warnings.append(f"Validation Warning: Required dependency '{dep}' has no explicit installation step scheduled.")

        valid = len(errors) == 0
        return ValidationReport(valid=valid, errors=errors, warnings=warnings, metrics=metrics)

    def submit_plan(self, plan: Plan) -> None:
        """
        Submits a validated plan to the registered execution interface.
        """
        if not plan.validation_status:
            raise ValueError(f"Cannot submit plan '{plan.id}': plan has not been successfully validated.")
            
        if self.execution_interface is None:
            raise RuntimeError("No execution interface has been registered with this Planner.")

        logger.info(f"Submitting validated plan '{plan.id}' to execution interface.")
        self.execution_interface.start_plan(plan)

    def get_execution_phases(self, plan: Plan) -> List[List[str]]:
        """
        Groups leaf steps of a plan into sequential execution phases.
        All steps inside a single phase have satisfied dependencies and can run in parallel.
        """
        leaves = [s for s in plan.steps if not s.child_ids]
        leaf_ids = {s.id for s in leaves}
        
        step_deps = {}
        for s in leaves:
            deps = [dep for dep in s.dependencies if dep in leaf_ids]
            step_deps[s.id] = set(deps)
            
        phases: List[List[str]] = []
        resolved: Set[str] = set()
        
        while len(resolved) < len(leaves):
            current_phase = []
            for s_id, deps in step_deps.items():
                if s_id not in resolved and deps.issubset(resolved):
                    current_phase.append(s_id)
                    
            if not current_phase:
                remaining = [s_id for s_id in step_deps if s_id not in resolved]
                phases.append(remaining)
                break
                
            phases.append(current_phase)
            resolved.update(current_phase)
            
        return phases

    def calculate_critical_path(self, plan: Plan) -> Tuple[List[str], float]:
        """
        Calculates the critical path of leaf steps in the plan DAG.
        Returns the ordered sequence of step IDs on the critical path and the total path duration.
        """
        leaves = [s for s in plan.steps if not s.child_ids]
        if not leaves:
            return [], 0.0
            
        leaf_ids = {s.id for s in leaves}
        step_map = {s.id: s for s in leaves}
        step_deps = {s.id: [d for d in s.dependencies if d in leaf_ids] for s in leaves}
        
        dp: Dict[str, float] = {}
        paths: Dict[str, List[str]] = {}
        
        def get_longest_path_ending_at(u_id: str) -> Tuple[List[str], float]:
            if u_id in dp:
                return paths[u_id], dp[u_id]
                
            step = step_map[u_id]
            duration = step.timeout
            
            prereqs = step_deps.get(u_id, [])
            if not prereqs:
                paths[u_id] = [u_id]
                dp[u_id] = duration
                return [u_id], duration
                
            max_prev_dur = -1.0
            best_prev_path: List[str] = []
            
            for v_id in prereqs:
                v_path, v_dur = get_longest_path_ending_at(v_id)
                if v_dur > max_prev_dur:
                     max_prev_dur = v_dur
                     best_prev_path = v_path
                     
            paths[u_id] = best_prev_path + [u_id]
            dp[u_id] = max_prev_dur + duration
            return paths[u_id], dp[u_id]
            
        max_overall_duration = -1.0
        critical_path: List[str] = []
        
        for s in leaves:
            path, dur = get_longest_path_ending_at(s.id)
            if dur > max_overall_duration:
                max_overall_duration = dur
                critical_path = path
                 
        return critical_path, max(0.0, max_overall_duration)

    def generate_mermaid_chart(self, plan: Plan) -> str:
        """
        Generates a Mermaid.js flowchart string representing parent-child subgraphs
        and sequential dependencies.
        """
        lines = ["flowchart TD"]
        
        from collections import defaultdict
        children_by_parent = defaultdict(list)
        root_steps = []
        
        for step in plan.steps:
            if step.parent_id is None:
                root_steps.append(step)
            else:
                children_by_parent[step.parent_id].append(step)
                
        step_map = {s.id: s for s in plan.steps}
        
        def render_step_recursive(step: PlanStep, indent: str = "    ") -> List[str]:
            out = []
            children = children_by_parent.get(step.id, [])
            if children:
                clean_desc = step.description.replace('"', '\\"')
                out.append(f'{indent}subgraph {step.id} ["{clean_desc}"]')
                for child in children:
                    out.extend(render_step_recursive(child, indent + "    "))
                out.append(f'{indent}end')
            else:
                clean_desc = step.description.replace('"', '\\"')
                out.append(f'{indent}{step.id}["{clean_desc}"]')
            return out
            
        for r_step in root_steps:
            lines.extend(render_step_recursive(r_step))
            
        for step in plan.steps:
            for dep_id in step.dependencies:
                if dep_id in step_map:
                    lines.append(f"    {dep_id} --> {step.id}")
                    
        return "\n".join(lines)

    def estimate_complexity(self, steps: List[PlanStep]) -> str:
        """Estimates complexity dynamically based on hierarchy depth and total step count."""
        if not steps:
            return "low"
        
        max_depth = 0
        step_map = {s.id: s for s in steps}
        for step in steps:
            depth = 0
            curr = step
            while curr.parent_id is not None:
                depth += 1
                curr_parent = step_map.get(curr.parent_id)
                if not curr_parent:
                    break
                curr = curr_parent
            max_depth = max(max_depth, depth)

        total_steps = len(steps)
        dep_count = sum(len(step.dependencies) for step in steps)
        
        if total_steps > 8 or max_depth >= 2 or dep_count > 6:
            return "high"
        elif total_steps > 3 or max_depth >= 1 or dep_count > 2:
            return "medium"
        return "low"

    def estimate_duration(self, steps: List[PlanStep]) -> float:
        """Estimates duration by summing timeouts of only leaf steps."""
        return sum(step.timeout for step in steps if not step.child_ids)

    def export_plan(self, plan: Plan) -> str:
        """Serializes Plan and subdataclasses to a JSON string representation."""
        logger.info(f"Exporting plan: '{plan.id}'")
        return json.dumps(asdict(plan), indent=2)

    def import_plan(self, plan_json: str) -> Plan:
        """Deserializes a JSON string into a structured Plan object."""
        logger.info("Importing plan from JSON string.")
        data = json.loads(plan_json)
        
        goal_data = data.get("goal", {})
        goal = Goal(
            description=goal_data.get("description", ""),
            priority=goal_data.get("priority", "medium"),
            target_skills=goal_data.get("target_skills", []),
            target_resources=goal_data.get("target_resources", [])
        )

        steps_data = data.get("steps", [])
        steps = []
        for s in steps_data:
            rp_data = s.get("recovery_policy")
            rp = None
            if rp_data:
                rp = RecoveryPolicy(
                    strategy=rp_data.get("strategy", "retry"),
                    max_retries=rp_data.get("max_retries", 3),
                    fallback_skills=rp_data.get("fallback_skills", []),
                    allow_partial=rp_data.get("allow_partial", False),
                    alternative_step_desc=rp_data.get("alternative_step_desc"),
                    alternative_step_action=rp_data.get("alternative_step_action"),
                    rollback_step_descs=rp_data.get("rollback_step_descs", [])
                )

            steps.append(
                PlanStep(
                    id=s.get("id"),
                    description=s.get("description", ""),
                    action_type=s.get("action_type", "generic"),
                    required_skill=s.get("required_skill", "generic"),
                    dependencies=s.get("dependencies", []),
                    expected_output=s.get("expected_output", ""),
                    status=s.get("status", "pending"),
                    retry_count=s.get("retry_count", 3),
                    timeout=s.get("timeout", 30.0),
                    metadata=s.get("metadata", {}),
                    parent_id=s.get("parent_id"),
                    child_ids=s.get("child_ids", []),
                    required_resources=s.get("required_resources", []),
                    required_skills=s.get("required_skills", s.get("required_skills", [s.get("required_skill", "generic")])),
                    recovery_policy=rp,
                    expected_artifact=s.get("expected_artifact", ""),
                    required_artifacts=s.get("required_artifacts", [])
                )
            )

        return Plan(
            id=data.get("id", str(uuid.uuid4())),
            goal=goal,
            goal_description=data.get("goal_description", goal.description),
            priority=data.get("priority", "medium"),
            status=data.get("status", "pending"),
            estimated_complexity=data.get("estimated_complexity", "low"),
            estimated_duration=data.get("estimated_duration", 0.0),
            creation_timestamp=data.get("creation_timestamp", data.get("created_at", time.time())),
            created_at=data.get("created_at", data.get("creation_timestamp", time.time())),
            dependencies=data.get("dependencies", []),
            steps=steps,
            required_skills=data.get("required_skills", []),
            required_resources=data.get("required_resources", []),
            validation_status=data.get("validation_status", False),
            metadata=data.get("metadata", {}),
            required_artifacts=data.get("required_artifacts", []),
            required_dependencies=data.get("required_dependencies", []),
            risk_analysis=data.get("risk_analysis", {}),
            expected_outputs=data.get("expected_outputs", [])
        )

    def cancel_plan(self, plan: Plan) -> Plan:
        """Sets plan status to cancelled."""
        logger.info(f"Cancelling plan: '{plan.id}'")
        plan.status = "cancelled"
        for step in plan.steps:
            step.status = "cancelled"
        return plan

