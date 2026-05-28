from typing import Any, Dict, List, Optional, TypedDict


class ChallanState(TypedDict, total=False):
    request_id: str
    mode: str
    user_type: str
    user_name: str
    input_vehicle_number: str
    selected_state: str
    challan_file_path: str
    vehicle_front_file_path: str
    challan_ocr_text: str
    vehicle_ocr_text: str
    vehicle_number: str
    vehicle_number_from_vehicle_image: str
    vehicle_match_status: str
    place_of_violation: str
    vehicle_type: str
    evidence_timestamp: str
    multiple_offences: bool
    offence_rows: List[Dict[str, Any]]
    latest_offence: str
    latest_offence_location: str
    latest_offence_datetime: str
    latest_fine_amount: int
    evidence_matches_latest_timestamp: bool
    legal_reference_groups: Dict[str, List[str]]
    offence: str
    fine_amount: int
    expected_fine: int
    expected_fine_text: str
    date_time: str
    ocr_confidence: int
    image_quality: str
    validation_issues: List[str]
    retrieved_sections: List[Dict[str, Any]]
    legal_analysis: str
    confidence_score: int
    final_status: str
    recommendation: List[str]
    final_report: str
    report_pdf_path: str
    execution_log: List[str]
    legal_question: Optional[str]
    legal_answer: Optional[str]
    guardrail_result: Dict[str, Any]
    judge_result: Dict[str, Any]
