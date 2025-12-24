"""
Eligibility Engine Tool
Checks user eligibility for various government schemes
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..agent.core import BaseTool


class EligibilityChecker(BaseTool):
    """
    Tool for checking user eligibility against government schemes
    This is a critical tool for the agent to determine which schemes apply
    """
    
    @property
    def name(self) -> str:
        return "eligibility_checker"
    
    @property
    def description(self) -> str:
        return """पात्रता तपासणी साधन - वापरकर्त्याची सरकारी योजनांसाठी पात्रता तपासते.
Eligibility checking tool - checks user eligibility for government schemes based on their profile."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "age": {
                "type": "integer",
                "description": "वापरकर्त्याचे वय / User's age",
                "required": False
            },
            "income": {
                "type": "number",
                "description": "वार्षिक उत्पन्न / Annual income in rupees",
                "required": False
            },
            "gender": {
                "type": "string",
                "description": "लिंग / Gender (male/female/other)",
                "required": False
            },
            "caste_category": {
                "type": "string",
                "description": "जात वर्ग / Caste category (SC/ST/OBC/General)",
                "required": False
            },
            "state": {
                "type": "string",
                "description": "राज्य / State",
                "required": False
            },
            "is_farmer": {
                "type": "boolean",
                "description": "शेतकरी आहे का / Is the user a farmer",
                "required": False
            },
            "is_bpl": {
                "type": "boolean",
                "description": "दारिद्र्य रेषेखाली / Below poverty line",
                "required": False
            },
            "education": {
                "type": "string",
                "description": "शिक्षण / Education level",
                "required": False
            },
            "occupation": {
                "type": "string",
                "description": "व्यवसाय / Occupation",
                "required": False
            },
            "family_size": {
                "type": "integer",
                "description": "कुटुंबातील सदस्य संख्या / Family size",
                "required": False
            },
            "has_land": {
                "type": "boolean",
                "description": "जमीन आहे का / Owns agricultural land",
                "required": False
            },
            "land_size": {
                "type": "number",
                "description": "जमिनीचे क्षेत्रफळ एकरमध्ये / Land size in acres",
                "required": False
            },
            "is_widow": {
                "type": "boolean",
                "description": "विधवा आहे का / Is widow",
                "required": False
            },
            "is_disabled": {
                "type": "boolean",
                "description": "अपंग आहे का / Is disabled",
                "required": False
            },
            "scheme_categories": {
                "type": "array",
                "description": "योजना प्रकार / Scheme categories to check",
                "required": False
            }
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Check eligibility for schemes based on user profile"""
        # Extract user profile
        profile = UserProfile(**kwargs)
        
        # Get all schemes
        schemes = self._get_all_schemes()
        
        # Check eligibility for each scheme
        eligible_schemes = []
        ineligible_schemes = []
        missing_info_schemes = []
        
        for scheme in schemes:
            result = self._check_scheme_eligibility(scheme, profile)
            
            if result["status"] == "eligible":
                eligible_schemes.append({
                    "scheme": scheme,
                    "match_score": result["match_score"],
                    "matched_criteria": result["matched_criteria"]
                })
            elif result["status"] == "ineligible":
                ineligible_schemes.append({
                    "scheme_name": scheme["name"],
                    "reason": result["reason"]
                })
            else:
                missing_info_schemes.append({
                    "scheme_name": scheme["name"],
                    "missing_fields": result["missing_fields"]
                })
        
        # Sort by match score
        eligible_schemes.sort(key=lambda x: x["match_score"], reverse=True)
        
        return {
            "eligible_schemes": eligible_schemes,
            "ineligible_reasons": ineligible_schemes,
            "needs_more_info": missing_info_schemes,
            "total_checked": len(schemes),
            "total_eligible": len(eligible_schemes),
            "timestamp": datetime.now().isoformat()
        }
    
    def _check_scheme_eligibility(self, 
                                  scheme: Dict[str, Any], 
                                  profile: 'UserProfile') -> Dict[str, Any]:
        """Check if user is eligible for a specific scheme"""
        criteria = scheme.get("eligibility_criteria", {})
        matched = []
        failed = []
        missing = []
        
        # Check age criteria
        if "min_age" in criteria or "max_age" in criteria:
            if profile.age is None:
                missing.append("age")
            else:
                min_age = criteria.get("min_age", 0)
                max_age = criteria.get("max_age", 150)
                if min_age <= profile.age <= max_age:
                    matched.append("age")
                else:
                    failed.append(f"वय {min_age}-{max_age} वर्षे असणे आवश्यक")
        
        # Check income criteria
        if "max_income" in criteria:
            if profile.income is None:
                missing.append("income")
            else:
                if profile.income <= criteria["max_income"]:
                    matched.append("income")
                else:
                    failed.append(f"उत्पन्न ₹{criteria['max_income']} पेक्षा कमी असणे आवश्यक")
        
        # Check gender criteria
        if "gender" in criteria:
            if profile.gender is None:
                missing.append("gender")
            else:
                if profile.gender in criteria["gender"]:
                    matched.append("gender")
                else:
                    failed.append(f"फक्त {', '.join(criteria['gender'])} साठी")
        
        # Check caste category
        if "caste_categories" in criteria:
            if profile.caste_category is None:
                missing.append("caste_category")
            else:
                if profile.caste_category in criteria["caste_categories"]:
                    matched.append("caste_category")
                else:
                    failed.append(f"फक्त {', '.join(criteria['caste_categories'])} वर्गासाठी")
        
        # Check state
        if "states" in criteria:
            if profile.state is None:
                missing.append("state")
            else:
                if profile.state.lower() in [s.lower() for s in criteria["states"]]:
                    matched.append("state")
                else:
                    failed.append(f"फक्त {', '.join(criteria['states'])} राज्यांसाठी")
        
        # Check farmer status
        if criteria.get("is_farmer") == True:
            if profile.is_farmer is None:
                missing.append("is_farmer")
            elif not profile.is_farmer:
                failed.append("फक्त शेतकऱ्यांसाठी")
            else:
                matched.append("is_farmer")
        
        # Check BPL status
        if criteria.get("is_bpl") == True:
            if profile.is_bpl is None:
                missing.append("is_bpl")
            elif not profile.is_bpl:
                failed.append("फक्त BPL कुटुंबांसाठी")
            else:
                matched.append("is_bpl")
        
        # Check land ownership
        if "max_land_size" in criteria:
            if profile.has_land is None or profile.land_size is None:
                missing.append("land_size")
            else:
                if profile.land_size <= criteria["max_land_size"]:
                    matched.append("land_size")
                else:
                    failed.append(f"जमीन {criteria['max_land_size']} एकर पेक्षा कमी असणे आवश्यक")
        
        # Check widow status
        if criteria.get("is_widow") == True:
            if profile.is_widow is None:
                missing.append("is_widow")
            elif not profile.is_widow:
                failed.append("फक्त विधवांसाठी")
            else:
                matched.append("is_widow")
        
        # Check disability
        if criteria.get("is_disabled") == True:
            if profile.is_disabled is None:
                missing.append("is_disabled")
            elif not profile.is_disabled:
                failed.append("फक्त अपंग व्यक्तींसाठी")
            else:
                matched.append("is_disabled")
        
        # Determine result
        if failed:
            return {
                "status": "ineligible",
                "reason": "; ".join(failed),
                "matched_criteria": matched
            }
        elif missing:
            return {
                "status": "unknown",
                "missing_fields": missing,
                "matched_criteria": matched
            }
        else:
            # Calculate match score
            total_criteria = len(criteria)
            match_score = len(matched) / max(total_criteria, 1)
            
            return {
                "status": "eligible",
                "match_score": match_score,
                "matched_criteria": matched
            }
    
    def _get_all_schemes(self) -> List[Dict[str, Any]]:
        """Get all available schemes"""
        # This would typically come from a database
        # For now, return mock schemes
        return GOVERNMENT_SCHEMES


class UserProfile:
    """User profile for eligibility checking"""
    
    def __init__(self, 
                 age: Optional[int] = None,
                 income: Optional[float] = None,
                 gender: Optional[str] = None,
                 caste_category: Optional[str] = None,
                 state: Optional[str] = None,
                 is_farmer: Optional[bool] = None,
                 is_bpl: Optional[bool] = None,
                 education: Optional[str] = None,
                 occupation: Optional[str] = None,
                 family_size: Optional[int] = None,
                 has_land: Optional[bool] = None,
                 land_size: Optional[float] = None,
                 is_widow: Optional[bool] = None,
                 is_disabled: Optional[bool] = None,
                 **kwargs):
        self.age = age
        self.income = income
        self.gender = gender
        self.caste_category = caste_category
        self.state = state
        self.is_farmer = is_farmer
        self.is_bpl = is_bpl
        self.education = education
        self.occupation = occupation
        self.family_size = family_size
        self.has_land = has_land
        self.land_size = land_size
        self.is_widow = is_widow
        self.is_disabled = is_disabled


# Mock Government Schemes Database (Marathi)
GOVERNMENT_SCHEMES = [
    {
        "id": "pmksy",
        "name": "प्रधानमंत्री किसान सन्मान निधी (PM-KISAN)",
        "name_en": "PM Kisan Samman Nidhi",
        "description": "शेतकऱ्यांना वार्षिक ₹6000 आर्थिक सहाय्य",
        "description_en": "Annual financial assistance of ₹6000 to farmers",
        "category": "agriculture",
        "benefits": [
            "वार्षिक ₹6000 (3 हप्त्यांमध्ये)",
            "थेट बँक खात्यात जमा"
        ],
        "eligibility_criteria": {
            "is_farmer": True,
            "max_land_size": 5.0
        },
        "documents_required": [
            "आधार कार्ड",
            "जमीन मालकी कागदपत्रे",
            "बँक पासबुक"
        ],
        "application_process": [
            "नजीकच्या CSC केंद्रात जा",
            "ऑनलाइन नोंदणी करा",
            "कागदपत्रे सादर करा"
        ],
        "website": "https://pmkisan.gov.in"
    },
    {
        "id": "pmay",
        "name": "प्रधानमंत्री आवास योजना (PMAY)",
        "name_en": "Pradhan Mantri Awas Yojana",
        "description": "गरीब कुटुंबांना स्वस्त घरे",
        "description_en": "Affordable housing for poor families",
        "category": "housing",
        "benefits": [
            "₹2.5 लाखांपर्यंत अनुदान",
            "कमी व्याजदराने कर्ज"
        ],
        "eligibility_criteria": {
            "max_income": 300000,
            "is_bpl": True
        },
        "documents_required": [
            "आधार कार्ड",
            "उत्पन्न प्रमाणपत्र",
            "रहिवास प्रमाणपत्र"
        ],
        "application_process": [
            "ग्रामपंचायत/नगरपालिकेत अर्ज करा",
            "ऑनलाइन अर्ज करता येतो"
        ],
        "website": "https://pmaymis.gov.in"
    },
    {
        "id": "sby",
        "name": "महात्मा ज्योतिराव फुले जन आरोग्य योजना",
        "name_en": "Mahatma Jyotirao Phule Jan Arogya Yojana",
        "description": "मोफत आरोग्य विमा (महाराष्ट्र)",
        "description_en": "Free health insurance (Maharashtra)",
        "category": "health",
        "benefits": [
            "₹1.5 लाखांपर्यंत मोफत उपचार",
            "971 रोगांचा समावेश"
        ],
        "eligibility_criteria": {
            "states": ["Maharashtra", "महाराष्ट्र"],
            "max_income": 100000
        },
        "documents_required": [
            "पिवळे/केशरी रेशन कार्ड",
            "आधार कार्ड"
        ],
        "application_process": [
            "नजीकच्या सरकारी रुग्णालयात संपर्क करा"
        ],
        "website": "https://www.jeevandayee.gov.in"
    },
    {
        "id": "widow_pension",
        "name": "विधवा पेन्शन योजना",
        "name_en": "Widow Pension Scheme",
        "description": "विधवा महिलांना मासिक पेन्शन",
        "description_en": "Monthly pension for widows",
        "category": "pension",
        "benefits": [
            "मासिक ₹1000 पेन्शन",
            "थेट बँक खात्यात"
        ],
        "eligibility_criteria": {
            "is_widow": True,
            "gender": ["female", "महिला"],
            "max_income": 100000
        },
        "documents_required": [
            "पतीचा मृत्यू प्रमाणपत्र",
            "आधार कार्ड",
            "उत्पन्न प्रमाणपत्र"
        ],
        "application_process": [
            "तहसील कार्यालयात अर्ज करा"
        ],
        "website": "https://sjsa.maharashtra.gov.in"
    },
    {
        "id": "disability_pension",
        "name": "अपंग पेन्शन योजना",
        "name_en": "Disability Pension Scheme",
        "description": "अपंग व्यक्तींना मासिक पेन्शन",
        "description_en": "Monthly pension for persons with disabilities",
        "category": "pension",
        "benefits": [
            "मासिक ₹1000-2000 पेन्शन",
            "वैद्यकीय सहाय्य"
        ],
        "eligibility_criteria": {
            "is_disabled": True,
            "max_income": 100000
        },
        "documents_required": [
            "अपंगत्व प्रमाणपत्र (40% पेक्षा जास्त)",
            "आधार कार्ड",
            "उत्पन्न प्रमाणपत्र"
        ],
        "application_process": [
            "तहसील कार्यालयात अर्ज करा"
        ],
        "website": "https://sjsa.maharashtra.gov.in"
    },
    {
        "id": "pmjdy",
        "name": "प्रधानमंत्री जन धन योजना",
        "name_en": "Pradhan Mantri Jan Dhan Yojana",
        "description": "शून्य बॅलन्स बँक खाते",
        "description_en": "Zero balance bank account",
        "category": "financial",
        "benefits": [
            "शून्य बॅलन्स खाते",
            "₹2 लाख अपघात विमा",
            "RuPay डेबिट कार्ड"
        ],
        "eligibility_criteria": {
            "min_age": 10
        },
        "documents_required": [
            "आधार कार्ड किंवा मतदार ओळखपत्र",
            "पासपोर्ट आकाराचा फोटो"
        ],
        "application_process": [
            "कोणत्याही बँकेत जा",
            "अर्ज भरा आणि खाते उघडा"
        ],
        "website": "https://pmjdy.gov.in"
    },
    {
        "id": "pmsby",
        "name": "प्रधानमंत्री सुरक्षा बीमा योजना",
        "name_en": "Pradhan Mantri Suraksha Bima Yojana",
        "description": "स्वस्त अपघात विमा",
        "description_en": "Affordable accident insurance",
        "category": "insurance",
        "benefits": [
            "₹2 लाख अपघात विमा",
            "फक्त ₹12 वार्षिक प्रीमियम"
        ],
        "eligibility_criteria": {
            "min_age": 18,
            "max_age": 70
        },
        "documents_required": [
            "आधार कार्ड",
            "बँक खाते"
        ],
        "application_process": [
            "बँकेत अर्ज करा",
            "ऑटो-डेबिट मंजूर करा"
        ],
        "website": "https://www.jansuraksha.gov.in"
    },
    {
        "id": "scholarship_sc",
        "name": "अनुसूचित जाती शिष्यवृत्ती",
        "name_en": "SC Scholarship Scheme",
        "description": "SC विद्यार्थ्यांसाठी शिष्यवृत्ती",
        "description_en": "Scholarship for SC students",
        "category": "education",
        "benefits": [
            "शिक्षण शुल्क माफी",
            "मासिक भत्ता"
        ],
        "eligibility_criteria": {
            "caste_categories": ["SC"],
            "min_age": 16,
            "max_age": 30,
            "max_income": 250000
        },
        "documents_required": [
            "जात प्रमाणपत्र",
            "उत्पन्न प्रमाणपत्र",
            "शाळा/कॉलेज प्रमाणपत्र"
        ],
        "application_process": [
            "महाDBT पोर्टलवर ऑनलाइन अर्ज करा"
        ],
        "website": "https://mahadbt.maharashtra.gov.in"
    },
    {
        "id": "ladki_bahin",
        "name": "मुख्यमंत्री माझी लाडकी बहीण योजना",
        "name_en": "Mukhyamantri Majhi Ladki Bahin Yojana",
        "description": "महिलांना मासिक आर्थिक सहाय्य (महाराष्ट्र)",
        "description_en": "Monthly financial assistance to women (Maharashtra)",
        "category": "women_welfare",
        "benefits": [
            "मासिक ₹1500 आर्थिक सहाय्य",
            "थेट बँक खात्यात जमा"
        ],
        "eligibility_criteria": {
            "gender": ["female", "महिला"],
            "min_age": 21,
            "max_age": 65,
            "max_income": 250000,
            "states": ["Maharashtra", "महाराष्ट्र"]
        },
        "documents_required": [
            "आधार कार्ड",
            "उत्पन्न प्रमाणपत्र",
            "रहिवास प्रमाणपत्र",
            "बँक पासबुक"
        ],
        "application_process": [
            "ऑनलाइन पोर्टलवर नोंदणी करा",
            "ग्रामसेवक/नगरपालिकेत अर्ज करा"
        ],
        "website": "https://womenchild.maharashtra.gov.in"
    },
    {
        "id": "old_age_pension",
        "name": "वृद्धापकाळ पेन्शन योजना",
        "name_en": "Old Age Pension Scheme",
        "description": "वृद्ध नागरिकांना मासिक पेन्शन",
        "description_en": "Monthly pension for senior citizens",
        "category": "pension",
        "benefits": [
            "मासिक ₹1000-1500 पेन्शन",
            "थेट बँक खात्यात"
        ],
        "eligibility_criteria": {
            "min_age": 65,
            "max_income": 100000
        },
        "documents_required": [
            "आधार कार्ड",
            "वय प्रमाणपत्र",
            "उत्पन्न प्रमाणपत्र"
        ],
        "application_process": [
            "तहसील कार्यालयात अर्ज करा",
            "सेतू केंद्रात अर्ज करा"
        ],
        "website": "https://sjsa.maharashtra.gov.in"
    }
]
