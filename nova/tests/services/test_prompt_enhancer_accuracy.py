import unittest
from nova.ai.prompt_validator import PromptValidator
from nova.ai.prompt_enhancer import PromptEnhancer

class TestPromptEnhancerAccuracy(unittest.TestCase):
    # Definition of 100 test prompts with their expected bypass state and category
    SAMPLE_PROMPTS = [
        # --- SIMPLE PROMPTS (Bypass = True) ---
        ("hi", True, "greeting"),
        ("hello", True, "greeting"),
        ("how are you", True, "greeting"),
        ("good morning", True, "greeting"),
        ("what is 5+5", True, "math"),
        ("what is 20 * 4", True, "math"),
        ("50 divided by 2", True, "math"),
        ("continue", True, "continuation"),
        ("explain more", True, "continuation"),
        ("summarize", True, "continuation"),
        ("simplify", True, "continuation"),
        ("give example", True, "continuation"),
        ("new chat", True, "continuation"),
        ("start a new chat", True, "continuation"),
        ("clear chat", True, "continuation"),
        ("what time is it", True, "general"),
        ("who am I speaking to", True, "general"),
        ("yes", True, "general"),
        ("no", True, "general"),
        ("ok", True, "general"),
        ("thanks", True, "general"),
        ("thank you", True, "general"),
        ("open google", True, "command"),
        ("open chatgpt", True, "command"),
        ("stop", True, "command"),
        ("go back", True, "command"),
        ("tell me a joke", True, "general"),
        ("sing a song", True, "general"),
        ("help me", True, "general"),
        ("test", True, "general"),

        # --- CODING PROMPTS (Bypass = False) ---
        ("write a quicksort in python", False, "coding"),
        ("how to write binary search in rust", False, "coding"),
        ("implement a websocket client in js", False, "coding"),
        ("create a simple database connection in c#", False, "coding"),
        ("show me a dockerfile for django app", False, "coding"),
        ("write a script to scrape wikipedia", False, "coding"),
        ("how does garbage collection work in go", False, "coding"),
        ("explain recursion in computer science", False, "coding"),
        ("write sql query to count group rows", False, "coding"),
        ("implement bubble sort algorithm in c++", False, "coding"),
        ("show me a bash script to parse arguments", False, "coding"),
        ("how to deploy a flask app to aws", False, "coding"),
        ("write a regex to parse emails", False, "coding"),
        ("how to set up react router v6", False, "coding"),
        ("explain the difference between let and var", False, "coding"),
        ("write a unit test for python function", False, "coding"),
        ("how to resolve merge conflicts in git", False, "coding"),
        ("write css to center a div element", False, "coding"),
        ("create a mock API in node.js", False, "coding"),
        ("explain fast API route parameters", False, "coding"),
        ("write a Makefile to build c project", False, "coding"),
        ("how to write recursion stack limits", False, "coding"),
        ("write a powershell file copy script", False, "coding"),
        ("explain database index types btree", False, "coding"),
        ("how to handle cors in express", False, "coding"),

        # --- WRITING / DRAFTING PROMPTS (Bypass = False) ---
        ("draft an email to abhishek about status update", False, "writing"),
        ("write a formal apology letter to manager", False, "writing"),
        ("create a cover letter template for software job", False, "writing"),
        ("draft a short essay on AI ethics", False, "writing"),
        ("write a blog post outline on clean architecture", False, "writing"),
        ("create a checklist for project planning", False, "writing"),
        ("write a recommendation letter for coworker", False, "writing"),
        ("draft a response to a negative customer review", False, "writing"),
        ("write a poem about NixOS configurations", False, "writing"),
        ("create a slide deck outline on neural networks", False, "writing"),
        ("write a newsletter introduction paragraph", False, "writing"),
        ("draft a project proposal for client team", False, "writing"),
        ("write a product description for online shop", False, "writing"),
        ("create a recipe outline for chocolate cake", False, "writing"),
        ("write a press release for tech product launch", False, "writing"),
        ("draft a slack message announcing team lunch", False, "writing"),
        ("write a thank you note for interview opportunity", False, "writing"),
        ("create a meeting agenda template doc", False, "writing"),
        ("write a user bio description for portfolio", False, "writing"),
        ("draft a project delay notification email", False, "writing"),
        ("write a creative fiction intro story", False, "writing"),
        ("create a list of social media post captions", False, "writing"),
        ("write a description of scrum master role", False, "writing"),
        ("draft a contract termination letter copy", False, "writing"),
        ("write a policy draft for remote working", False, "writing"),

        # --- RESEARCH / COMPLEXITY PROMPTS (Bypass = False) ---
        ("compare rust and go memory management systems", False, "research"),
        ("explain standard model of physics in details", False, "research"),
        ("what is standard deviation formula statistics", False, "research"),
        ("explain keynesian economics theories briefly", False, "research"),
        ("compare sql and nosql database scaling strategies", False, "research"),
        ("explain quantum computing superposition concepts", False, "research"),
        ("what was the main cause of the French revolution", False, "research"),
        ("explain photosynthesis process in green plants", False, "research"),
        ("what is the difference between TCP and UDP", False, "research"),
        ("explain how public key cryptography works", False, "research"),
        ("compare docker containers vs virtual machines", False, "research"),
        ("explain plate tectonics continental drift", False, "research"),
        ("what is the theory of general relativity basics", False, "research"),
        ("explain cellular respiration steps overview", False, "research"),
        ("compare microservices vs monolithic architecture", False, "research"),
        ("explain the blockchain consensus proof of work", False, "research"),
        ("what is the function of mitochondria cell", False, "research"),
        ("explain how optical fibers transmit light data", False, "research"),
        ("compare git merge vs git rebase operations", False, "research"),
        ("explain inflation impacts on purchasing power", False, "research"),
    ]

    def test_prompt_validation_accuracy(self):
        passed_bypasses = 0
        passed_enhancements = 0
        total_prompts = len(self.SAMPLE_PROMPTS)

        for prompt, expected_bypass, category in self.SAMPLE_PROMPTS:
            is_simple = PromptValidator.is_simple(prompt)
            if is_simple == expected_bypass:
                if expected_bypass:
                    passed_bypasses += 1
                else:
                    passed_enhancements += 1
            else:
                print(f"FAILED bypass check: '{prompt}' (Expected bypass={expected_bypass}, got={is_simple})")

        total_passed = passed_bypasses + passed_enhancements
        accuracy = (total_passed / total_prompts) * 100.0
        
        print(f"\n--- Prompt Enhancer Accuracy Report ---")
        print(f"Total Prompts evaluated:  {total_prompts}")
        print(f"Correct Simple Bypasses:  {passed_bypasses}/30")
        print(f"Correct Complex Triggers: {passed_enhancements}/70")
        print(f"Overall Accuracy Score:   {accuracy:.2f}%")
        print(f"----------------------------------------")

        self.assertEqual(total_passed, total_prompts, f"Some bypass classifications failed! Accuracy: {accuracy:.2f}%")
