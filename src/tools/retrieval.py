"""
Scheme Retrieval Tool
RAG-based retrieval system for government schemes
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..agent.core import BaseTool


class SchemeRetriever(BaseTool):
    """
    Tool for retrieving relevant government schemes
    Uses semantic search to find schemes matching user query
    """
    
    def __init__(self, vector_store=None):
        self.vector_store = vector_store
        self._schemes_loaded = False
        self._schemes_cache = []
    
    @property
    def name(self) -> str:
        return "scheme_retriever"
    
    @property
    def description(self) -> str:
        return """योजना शोध साधन - वापरकर्त्याच्या प्रश्नावर आधारित सरकारी योजना शोधते.
Scheme search tool - finds government schemes based on user query."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "query": {
                "type": "string",
                "description": "शोध प्रश्न / Search query in any language",
                "required": True
            },
            "category": {
                "type": "string",
                "description": "योजना प्रकार / Scheme category (agriculture, housing, health, education, pension, financial, insurance, women_welfare)",
                "required": False
            },
            "state": {
                "type": "string",
                "description": "राज्य / State for state-specific schemes",
                "required": False
            },
            "limit": {
                "type": "integer",
                "description": "परिणाम मर्यादा / Maximum number of results",
                "required": False
            }
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Retrieve relevant schemes based on query"""
        query = kwargs.get("query", "")
        category = kwargs.get("category")
        state = kwargs.get("state")
        limit = kwargs.get("limit", 5)
        
        # Load schemes if not loaded
        if not self._schemes_loaded:
            self._load_schemes()
        
        # Search schemes
        if self.vector_store:
            # Use vector store for semantic search
            results = await self._semantic_search(query, limit)
        else:
            # Use keyword-based search
            results = self._keyword_search(query, limit)
        
        # Apply filters
        if category:
            results = [s for s in results if s.get("category") == category]
        
        if state:
            results = [
                s for s in results 
                if not s.get("eligibility_criteria", {}).get("states") or
                   state.lower() in [st.lower() for st in s.get("eligibility_criteria", {}).get("states", [])]
            ]
        
        # Format results
        formatted_results = []
        for scheme in results[:limit]:
            formatted_results.append({
                "id": scheme.get("id"),
                "name": scheme.get("name"),
                "name_en": scheme.get("name_en"),
                "description": scheme.get("description"),
                "category": scheme.get("category"),
                "benefits": scheme.get("benefits", []),
                "eligibility_summary": self._get_eligibility_summary(scheme),
                "documents_required": scheme.get("documents_required", []),
                "application_process": scheme.get("application_process", []),
                "website": scheme.get("website")
            })
        
        return {
            "schemes": formatted_results,
            "total_found": len(formatted_results),
            "query": query,
            "filters_applied": {
                "category": category,
                "state": state
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def _load_schemes(self):
        """Load schemes into cache"""
        from .eligibility import GOVERNMENT_SCHEMES
        self._schemes_cache = GOVERNMENT_SCHEMES
        self._schemes_loaded = True
    
    def _keyword_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Simple keyword-based search"""
        query_lower = query.lower()
        query_words = query_lower.split()
        
        scored_schemes = []
        for scheme in self._schemes_cache:
            score = 0
            
            # Search in name
            name = scheme.get("name", "").lower()
            name_en = scheme.get("name_en", "").lower()
            description = scheme.get("description", "").lower()
            description_en = scheme.get("description_en", "").lower()
            category = scheme.get("category", "").lower()
            
            text_to_search = f"{name} {name_en} {description} {description_en} {category}"
            
            for word in query_words:
                if word in text_to_search:
                    score += 1
                    
                    # Boost for exact match in name
                    if word in name or word in name_en:
                        score += 2
            
            # Category matching
            category_keywords = {
                "agriculture": ["शेती", "शेतकरी", "कृषी", "farmer", "farm", "agriculture", "किसान", "விவசாய", "விவசாயி", "விவசாயம்"],
                "housing": ["घर", "आवास", "house", "housing", "home", "வீடு", "வீட்டு", "வீடமைப்பு"],
                "health": ["आरोग्य", "उपचार", "रुग्णालय", "health", "hospital", "medical", "சுகாத", "மருத்துவ", "மருத்துவமனை"],
                "education": ["शिक्षण", "शाळा", "कॉलेज", "education", "school", "scholarship", "கல்வி", "பள்ளி", "கல்லூரி", "உதவித்தொகை"],
                "pension": ["पेन्शन", "निवृत्ती", "pension", "ஓய்வூதியம்"],
                "financial": ["पैसे", "आर्थिक", "बँक", "financial", "money", "bank"],
                "insurance": ["विमा", "insurance"],
                "women_welfare": ["महिला", "स्त्री", "women", "lady", "बहीण"]
            }
            
            for cat, keywords in category_keywords.items():
                if any(kw in query_lower for kw in keywords):
                    if scheme.get("category") == cat:
                        score += 3
            
            if score > 0:
                scored_schemes.append((score, scheme))
        
        # Sort by score
        scored_schemes.sort(key=lambda x: x[0], reverse=True)
        
        return [s[1] for s in scored_schemes[:limit]]
    
    async def _semantic_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Semantic search using vector store"""
        if not self.vector_store:
            return self._keyword_search(query, limit)
        
        # Query vector store
        results = await self.vector_store.similarity_search(query, k=limit)
        
        # Map results back to schemes
        scheme_ids = [r.metadata.get("scheme_id") for r in results]
        matched_schemes = [
            s for s in self._schemes_cache 
            if s.get("id") in scheme_ids
        ]
        
        return matched_schemes
    
    def _get_eligibility_summary(self, scheme: Dict[str, Any]) -> str:
        """Get human-readable eligibility summary"""
        criteria = scheme.get("eligibility_criteria", {})
        parts = []
        
        if "min_age" in criteria or "max_age" in criteria:
            min_age = criteria.get("min_age", 0)
            max_age = criteria.get("max_age", "")
            if max_age:
                parts.append(f"वय: {min_age}-{max_age} वर्षे")
            else:
                parts.append(f"वय: {min_age}+ वर्षे")
        
        if "max_income" in criteria:
            income = criteria["max_income"]
            if income >= 100000:
                parts.append(f"उत्पन्न: ₹{income/100000:.1f} लाखांपेक्षा कमी")
            else:
                parts.append(f"उत्पन्न: ₹{income} पेक्षा कमी")
        
        if criteria.get("is_farmer"):
            parts.append("शेतकरी असणे आवश्यक")
        
        if criteria.get("is_bpl"):
            parts.append("BPL कार्ड असणे आवश्यक")
        
        if "gender" in criteria:
            parts.append(f"लिंग: {', '.join(criteria['gender'])}")
        
        if "caste_categories" in criteria:
            parts.append(f"वर्ग: {', '.join(criteria['caste_categories'])}")
        
        if "states" in criteria:
            parts.append(f"राज्य: {', '.join(criteria['states'])}")
        
        return "; ".join(parts) if parts else "सर्वांसाठी उपलब्ध"


class ApplicationHelper(BaseTool):
    """
    Tool for helping users with scheme application process
    """
    
    @property
    def name(self) -> str:
        return "application_helper"
    
    @property
    def description(self) -> str:
        return """अर्ज सहाय्यक - योजनेसाठी अर्ज करण्यात मदत करते.
Application helper - assists with scheme application process."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "scheme_id": {
                "type": "string",
                "description": "योजना ID / Scheme ID to apply for",
                "required": True
            },
            "action": {
                "type": "string",
                "description": "कृती / Action (get_documents, get_process, check_status, find_office)",
                "required": True
            },
            "user_location": {
                "type": "string",
                "description": "वापरकर्त्याचे स्थान / User's location for finding nearby offices",
                "required": False
            }
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Provide application assistance"""
        scheme_id = kwargs.get("scheme_id")
        action = kwargs.get("action")
        user_location = kwargs.get("user_location")
        
        # Find scheme
        from .eligibility import GOVERNMENT_SCHEMES
        scheme = next(
            (s for s in GOVERNMENT_SCHEMES if s["id"] == scheme_id),
            None
        )
        
        if not scheme:
            return {
                "error": "योजना आढळली नाही / Scheme not found",
                "scheme_id": scheme_id
            }
        
        if action == "get_documents":
            return {
                "scheme_name": scheme["name"],
                "documents_required": scheme.get("documents_required", []),
                "message": "खालील कागदपत्रे तयार ठेवा / Keep following documents ready"
            }
        
        elif action == "get_process":
            return {
                "scheme_name": scheme["name"],
                "application_process": scheme.get("application_process", []),
                "website": scheme.get("website"),
                "message": "अर्ज करण्याची प्रक्रिया / Application process"
            }
        
        elif action == "check_status":
            # Mock status check
            return {
                "scheme_name": scheme["name"],
                "status": "pending",
                "message": "तुमचा अर्ज प्रक्रियेत आहे / Your application is being processed",
                "estimated_time": "15-30 दिवस / 15-30 days"
            }
        
        elif action == "find_office":
            # Mock nearby office finder
            offices = self._get_nearby_offices(scheme, user_location)
            return {
                "scheme_name": scheme["name"],
                "nearby_offices": offices,
                "message": "जवळचे कार्यालय / Nearby offices"
            }
        
        else:
            return {
                "error": "अज्ञात कृती / Unknown action",
                "valid_actions": ["get_documents", "get_process", "check_status", "find_office"]
            }
    
    def _get_nearby_offices(self, 
                           scheme: Dict[str, Any], 
                           location: Optional[str]) -> List[Dict[str, str]]:
        """Get mock nearby offices"""
        # In production, this would query a real database
        category = scheme.get("category", "")
        
        offices = {
            "agriculture": [
                {
                    "name": "तहसील कृषी कार्यालय",
                    "address": "तहसील कार्यालय परिसर",
                    "timing": "सोमवार-शनिवार, सकाळी 10 - संध्याकाळी 5"
                },
                {
                    "name": "CSC केंद्र",
                    "address": "ग्रामपंचायत कार्यालय",
                    "timing": "सोमवार-शुक्रवार, सकाळी 9 - संध्याकाळी 6"
                }
            ],
            "housing": [
                {
                    "name": "नगरपालिका कार्यालय",
                    "address": "मुख्य बाजार रोड",
                    "timing": "सोमवार-शनिवार, सकाळी 10 - संध्याकाळी 5"
                }
            ],
            "health": [
                {
                    "name": "जिल्हा रुग्णालय",
                    "address": "जिल्हा मुख्यालय",
                    "timing": "24 तास"
                }
            ],
            "pension": [
                {
                    "name": "तहसील कार्यालय",
                    "address": "तहसील मुख्यालय",
                    "timing": "सोमवार-शनिवार, सकाळी 10 - संध्याकाळी 5"
                },
                {
                    "name": "सेतू केंद्र",
                    "address": "जिल्हा परिषद परिसर",
                    "timing": "सोमवार-शुक्रवार, सकाळी 9 - संध्याकाळी 5"
                }
            ],
            "education": [
                {
                    "name": "समाज कल्याण विभाग",
                    "address": "जिल्हा परिषद कार्यालय",
                    "timing": "सोमवार-शुक्रवार, सकाळी 10 - संध्याकाळी 5"
                }
            ]
        }
        
        return offices.get(category, [
            {
                "name": "सेतू केंद्र",
                "address": "जिल्हा परिषद परिसर",
                "timing": "सोमवार-शुक्रवार, सकाळी 9 - संध्याकाळी 5"
            }
        ])
