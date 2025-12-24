"""
Executor Module
Responsible for executing tasks in the plan using registered tools
"""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from .core import (
    Plan, Task, TaskStatus, AgentContext, 
    ToolRegistry, StateMachine, AgentState
)


class ExecutionError(Exception):
    """Custom exception for execution errors"""
    def __init__(self, message: str, task_id: str, recoverable: bool = True):
        super().__init__(message)
        self.task_id = task_id
        self.recoverable = recoverable


class Executor:
    """
    Executor component of the agent
    Executes tasks from the plan using registered tools
    """
    
    def __init__(self, 
                 tool_registry: ToolRegistry, 
                 state_machine: StateMachine,
                 language: str = "marathi"):
        self.tool_registry = tool_registry
        self.state_machine = state_machine
        self.language = language
        self.execution_log: list = []
    
    async def execute_plan(self, 
                          plan: Plan, 
                          context: AgentContext) -> Dict[str, Any]:
        """
        Execute all tasks in the plan sequentially
        Returns execution results
        """
        results = {
            "plan_id": plan.id,
            "goal": plan.goal,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "task_results": [],
            "final_status": "success"
        }
        
        while not plan.is_complete:
            current_task = plan.get_current_task()
            if not current_task:
                break
            
            # Check dependencies
            if not self._check_dependencies(current_task, plan):
                current_task.status = TaskStatus.BLOCKED
                results["task_results"].append({
                    "task_id": current_task.id,
                    "status": "blocked",
                    "error": "Dependencies not met"
                })
                plan.advance()
                continue
            
            try:
                # Execute the task
                task_result = await self.execute_task(current_task, context)
                
                current_task.status = TaskStatus.COMPLETED
                current_task.result = task_result
                current_task.completed_at = datetime.now()
                
                results["tasks_completed"] += 1
                results["task_results"].append({
                    "task_id": current_task.id,
                    "status": "success",
                    "result": task_result
                })
                
                # Update context with task results
                self._update_context_from_result(current_task, task_result, context)
                
            except ExecutionError as e:
                current_task.status = TaskStatus.FAILED
                current_task.error = str(e)
                
                results["tasks_failed"] += 1
                results["task_results"].append({
                    "task_id": current_task.id,
                    "status": "failed",
                    "error": str(e),
                    "recoverable": e.recoverable
                })
                
                if not e.recoverable:
                    results["final_status"] = "failed"
                    break
                else:
                    # Log error but continue with next task
                    self._log_execution(
                        "error",
                        f"Task {current_task.id} failed but recoverable: {e}"
                    )
            
            # Move to next task
            plan.advance()
        
        if results["tasks_failed"] > 0 and results["final_status"] != "failed":
            results["final_status"] = "partial_success"
        
        return results
    
    async def execute_task(self, 
                          task: Task, 
                          context: AgentContext) -> Dict[str, Any]:
        """
        Execute a single task
        """
        task.status = TaskStatus.IN_PROGRESS
        
        self._log_execution(
            "info",
            f"Executing task: {task.id} - {task.description}"
        )
        
        if not task.tool_name:
            # Task without tool - might be a reasoning step
            return {"status": "completed", "message": "Reasoning step completed"}
        
        # Get the tool
        tool = self.tool_registry.get(task.tool_name)
        if not tool:
            raise ExecutionError(
                f"Tool not found: {task.tool_name}",
                task.id,
                recoverable=False
            )
        
        try:
            # Prepare parameters with context
            params = self._prepare_tool_params(task.tool_params, context)
            
            # Execute the tool
            result = await tool.execute(**params)
            
            self._log_execution(
                "info",
                f"Task {task.id} completed successfully"
            )
            
            return result
            
        except Exception as e:
            self._log_execution(
                "error",
                f"Task {task.id} execution failed: {str(e)}"
            )
            raise ExecutionError(str(e), task.id, recoverable=True)
    
    def _check_dependencies(self, task: Task, plan: Plan) -> bool:
        """Check if all task dependencies are met"""
        if not task.dependencies:
            return True
        
        for dep_id in task.dependencies:
            dep_task = next(
                (t for t in plan.tasks if t.id == dep_id), 
                None
            )
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        
        return True
    
    def _prepare_tool_params(self, 
                            params: Dict[str, Any], 
                            context: AgentContext) -> Dict[str, Any]:
        """
        Prepare tool parameters by resolving context references
        """
        prepared = {}
        
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$context."):
                # Resolve context reference
                context_key = value.replace("$context.", "")
                if context_key.startswith("profile."):
                    profile_key = context_key.replace("profile.", "")
                    prepared[key] = context.get_profile_value(profile_key)
                elif context_key.startswith("entity."):
                    entity_key = context_key.replace("entity.", "")
                    prepared[key] = context.extracted_entities.get(entity_key)
                else:
                    prepared[key] = value
            else:
                prepared[key] = value
        
        return prepared
    
    def _update_context_from_result(self, 
                                    task: Task, 
                                    result: Dict[str, Any],
                                    context: AgentContext):
        """Update context with information from task execution"""
        # Store task result in extracted entities
        context.extracted_entities[f"task_{task.id}_result"] = result
        
        # Extract specific fields based on tool type
        if task.tool_name == "eligibility_checker":
            if "eligible_schemes" in result:
                context.extracted_entities["eligible_schemes"] = result["eligible_schemes"]
            if "ineligible_reasons" in result:
                context.extracted_entities["ineligible_reasons"] = result["ineligible_reasons"]
        
        elif task.tool_name == "scheme_retriever":
            if "schemes" in result:
                context.extracted_entities["retrieved_schemes"] = result["schemes"]
        
        elif task.tool_name == "application_helper":
            if "application_status" in result:
                context.extracted_entities["application_status"] = result["application_status"]
    
    def _log_execution(self, level: str, message: str):
        """Log execution event"""
        self.execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        })
    
    def get_execution_log(self) -> list:
        """Get execution log"""
        return self.execution_log
    
    def clear_log(self):
        """Clear execution log"""
        self.execution_log = []
