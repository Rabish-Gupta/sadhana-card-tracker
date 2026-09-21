export type UserRole = "DEVOTEE" | "ADMIN";
export type AccountStatus = "PENDING" | "ACTIVE" | "INACTIVE" | "REJECTED";
export type RegistrationSource = "SELF_REGISTERED" | "ADMIN_CREATED";
export type ActivityCategory = "SADHANA" | "ACADEMIC";
export type ScoringType = "DAILY" | "WEEKLY_AGGREGATED" | "NON_SCORED" | "SYSTEM_DERIVED";
export type AggregationMethod = "SUM" | "AVERAGE" | "COUNT" | "MIN" | "MAX";
export type CardStatus = "IN_PROGRESS" | "FINALIZED";
export type ActivityInputType = "NUMBER" | "COUNT" | "DURATION" | "TIME" | "BOOLEAN" | "TEXT" | "SELECTION";
export type EmploymentStatus = "WORKING" | "NOT_WORKING";

export interface CategorySummary {
  id: string;
  code: string;
  display_name: string;
  academic_year: number | null;
}

export interface DevoteeProfilePublic {
  id: string;
  college: string;
  branch: string;
  college_joining_year: number;
  expected_graduation_year: number | null;
  current_academic_year: number | null;
  current_category: CategorySummary;
}

export interface UserPublic {
  id: string;
  full_name: string;
  email: string;
  phone_number: string;
  role: UserRole;
  account_status: AccountStatus;
  registration_source: RegistrationSource;
  approved_at: string | null;
  deactivated_at: string | null;
  created_at: string;
  devotee_profile: DevoteeProfilePublic | null;
}

export interface LoginRequest { email: string; password: string }
export interface AccessTokenResponse { access_token: string; token_type: string; expires_in: number }
export interface RegistrationRequest {
  full_name: string;
  email: string;
  password: string;
  phone_number: string;
  college: string;
  branch: string;
  current_academic_year: number;
  college_joining_year: number;
}
export interface RegistrationResponse {
  user_id: string;
  email: string;
  account_status: AccountStatus;
  message: string;
}

export interface DailyActivityValuePublic {
  field_id: string;
  field_key: string;
  label: string;
  input_type: ActivityInputType;
  unit_code: string | null;
  display_order: number;
  required_for_completion: boolean;
  is_filled: boolean;
  numeric_value: string;
  time_value: string | null;
  boolean_value: boolean | null;
  text_value: string | null;
}

export interface DailyActivityPublic {
  entry_id: string;
  activity_id: string;
  code: string;
  name: string;
  category: ActivityCategory;
  scoring_type: ScoringType;
  weekly_aggregation: AggregationMethod | null;
  is_system_derived: boolean;
  counts_toward_card_fill: boolean;
  is_filled: boolean;
  daily_score: number | null;
  max_score_snapshot: number | null;
  score_calculated_at: string | null;
  score_details: Record<string, unknown> | null;
  values: DailyActivityValuePublic[];
}

export interface DailyCardPublic {
  id: string;
  card_date: string;
  status: CardStatus;
  editable: boolean;
  category_code: string;
  category_name: string;
  first_update_at: string | null;
  last_update_at: string | null;
  finalized_at: string | null;
  timezone_snapshot: string;
  deadline_time_snapshot: string;
  deadline_at_utc: string;
  revision_number: number;
  activities: DailyActivityPublic[];
}

export interface DailyActivityValueUpdate {
  field_id: string;
  is_filled: boolean;
  numeric_value?: number | string | null;
  time_value?: string | null;
  boolean_value?: boolean | null;
  text_value?: string | null;
}

export interface DailyActivityUpdate {
  activity_id: string;
  values: DailyActivityValueUpdate[];
}

export interface DailyCardUpdateRequest {
  activities: DailyActivityUpdate[];
}

export interface PreviousWeekActivityPublic {
  week_start_date: string;
  raw_total: string | null;
  final_activity_score: number | null;
  maximum_score: number | null;
  standard_achievement: string | null;
}

export interface WeeklyActivityResultPublic {
  activity_id: string;
  code: string;
  name: string;
  category: ActivityCategory;
  scoring_type: ScoringType;
  aggregation_method: AggregationMethod | null;
  raw_total: string | null;
  daily_score_total: number | null;
  final_activity_score: number | null;
  maximum_score: number | null;
  rule_version_id?: string | null;
  standard_version_id?: string | null;
  standard_snapshot?: Record<string, unknown> | null;
  standard_achievement: string | null;
  calculation_details?: Record<string, unknown> | null;
  previous_week?: PreviousWeekActivityPublic | null;
}

export interface PreviousWeekEvaluationPublic {
  week_start_date: string;
  week_end_date: string;
  sadhana_score: number;
  sadhana_max_score: number;
  sadhana_percentage?: string | null;
  academic_score: number;
  academic_max_score: number;
  academic_percentage?: string | null;
}

export interface WeeklyEvaluationPublic {
  id: string;
  week_start_date: string;
  week_end_date: string;
  category_code: string;
  category_name: string;
  timezone_snapshot: string;
  sadhana_score: number;
  sadhana_max_score: number;
  sadhana_percentage?: string | null;
  academic_score: number;
  academic_max_score: number;
  academic_percentage?: string | null;
  revision_number: number;
  generated_at: string;
  updated_at: string;
  activities?: WeeklyActivityResultPublic[];
  previous_week?: PreviousWeekEvaluationPublic | null;
}

export interface FourWeekTrendPublic {
  first_percentage?: string | null;
  last_percentage?: string | null;
  change_percentage_points?: string | null;
  average_percentage?: string | null;
  minimum_percentage?: string | null;
  maximum_percentage?: string | null;
  range_percentage_points?: string | null;
}

export interface FourWeekScoreSummaryPublic {
  score: number;
  maximum_score: number;
  percentage?: string | null;
  trend: FourWeekTrendPublic;
}

export interface FourWeekWeekPublic {
  week_start_date: string;
  week_end_date: string;
  category_code: string;
  category_name: string;
  sadhana_score: number;
  sadhana_max_score: number;
  sadhana_percentage?: string | null;
  academic_score: number;
  academic_max_score: number;
  academic_percentage?: string | null;
}

export interface FourWeekActivityWeekPublic {
  week_start_date: string;
  week_end_date: string;
  raw_total?: string | null;
  final_activity_score?: number | null;
  maximum_score?: number | null;
  standard_achievement?: string | null;
  category_activity_config_id: string;
  rule_version_id?: string | null;
  standard_version_id?: string | null;
  standard_snapshot?: Record<string, unknown> | null;
}

export interface PreviousFourWeekActivityPublic {
  final_score_total?: number | null;
  maximum_score_total?: number | null;
  score_percentage?: string | null;
  raw_total_sum?: string | null;
  standard_achievement_average?: string | null;
}

export interface FourWeekActivityPublic {
  activity_id: string;
  code: string;
  name: string;
  category: ActivityCategory;
  scoring_types_seen?: ScoringType[];
  final_score_total?: number | null;
  maximum_score_total?: number | null;
  score_percentage?: string | null;
  raw_total_sum?: string | null;
  weekly_raw_totals?: Array<string | null>;
  weekly_final_scores?: Array<number | null>;
  weekly_maximum_scores?: Array<number | null>;
  weekly_results?: FourWeekActivityWeekPublic[];
  standard_achievement_average?: string | null;
  standard_periods_seen?: string[];
  daily_standard_achieved_days?: number | null;
  daily_standard_evaluated_days?: number | null;
  weekly_standard_met_weeks?: number | null;
  weekly_standard_evaluated_weeks?: number | null;
  previous_period?: PreviousFourWeekActivityPublic | null;
}

export interface PreviousFourWeekSummaryPublic {
  period_start_date: string;
  period_end_date: string;
  sadhana_score: number;
  sadhana_max_score: number;
  sadhana_percentage?: string | null;
  academic_score: number;
  academic_max_score: number;
  academic_percentage?: string | null;
  sadhana_change_percentage_points?: string | null;
  academic_change_percentage_points?: string | null;
}

export interface FourWeekReportPublic {
  period_start_date: string;
  period_end_date: string;
  weeks_count: number;
  definition?: string;
  weeks?: FourWeekWeekPublic[];
  sadhana: FourWeekScoreSummaryPublic;
  academic: FourWeekScoreSummaryPublic;
  activities?: FourWeekActivityPublic[];
  previous_period?: PreviousFourWeekSummaryPublic | null;
  observations?: string[];
  metadata?: Record<string, unknown>;
}

export interface PendingCategoryTransitionPublic {
  history_id: string;
  target_category_code: string;
  target_category_name: string;
  effective_from_week: string;
  change_source: string;
  reason: string;
}

export interface LifecycleStatusPublic {
  current_category_code: string;
  current_category_name: string;
  current_academic_year: number | null;
  next_promotion_week: string | null;
  sahadeva_review_due: boolean;
  bhima_choice_required: boolean;
  pending_category_transition: PendingCategoryTransitionPublic | null;
  pending_deactivation_week: string | null;
  pending_deactivation_reason: string | null;
}

export interface BhimaStatusChangeRequest {
  employment_status: EmploymentStatus;
  reason?: string;
}

export type RuleType = "BOOLEAN" | "THRESHOLD" | "PERCENTAGE" | "SYSTEM_DERIVED" | "NO_SCORE";
export type RoundingMode = "HALF_UP";
export type VersionStatus = "PENDING" | "ACTIVE" | "ARCHIVED";
export type StandardPeriod = "DAILY" | "WEEKLY";
export type SahadevaReviewDecision = "CONTINUE_TO_NAKULA" | "DEACTIVATE";

export interface AdminCategoryPublic extends CategorySummary {
  stage_order: number;
  is_active: boolean;
  is_archived: boolean;
}

export interface ActivityFieldPublic {
  id: string;
  field_key: string;
  label: string;
  input_type: ActivityInputType;
  unit_code: string | null;
  display_order: number;
  required_for_completion: boolean;
  is_active: boolean;
  is_archived: boolean;
}

export interface ActivityPublic {
  id: string;
  code: string;
  name: string;
  category: ActivityCategory;
  description: string | null;
  is_system_derived: boolean;
  is_active: boolean;
  is_archived: boolean;
  fields: ActivityFieldPublic[];
}

export interface ScoringRulePublic {
  id: string;
  activity_id: string;
  name: string;
  rule_type: RuleType;
  is_active: boolean;
  is_archived: boolean;
  created_by_id: string;
}

export interface ScoringRuleVersionPublic {
  id: string;
  scoring_rule_id: string;
  version_number: number;
  effective_from_week: string;
  status: VersionStatus;
  max_score: number;
  rounding_mode: RoundingMode;
  configuration: Record<string, unknown>;
  created_by_id: string;
  created_at: string;
}

export interface StandardPublic {
  id: string;
  activity_id: string;
  name: string;
  is_active: boolean;
  is_archived: boolean;
  created_by_id: string;
}

export interface StandardVersionPublic {
  id: string;
  standard_id: string;
  version_number: number;
  effective_from_week: string;
  period: StandardPeriod;
  target_definition: Record<string, unknown>;
  status: VersionStatus;
  created_by_id: string;
  created_at: string;
}

export interface CategoryActivityConfigPublic {
  id: string;
  organization_id: string;
  category_id: string;
  activity_id: string;
  version_number: number;
  effective_from_week: string;
  is_applicable: boolean;
  scoring_type: ScoringType;
  weekly_aggregation: AggregationMethod | null;
  scoring_rule_id: string | null;
  standard_id: string | null;
  counts_toward_card_fill: boolean;
  status: VersionStatus;
  created_by_id: string;
  created_at: string;
}

export interface OrganizationSettingVersionPublic {
  id: string;
  organization_id: string;
  version_number: number;
  effective_from_week: string;
  status: VersionStatus;
  timezone: string;
  week_start_day: number;
  daily_finalize_time: string;
  promotion_month: number;
  created_by_id: string | null;
  created_at: string;
}

export interface SahadevaReviewItem {
  user_id: string;
  full_name: string;
  email: string;
  due_week: string;
  review_due: boolean;
  pending_decision: SahadevaReviewDecision | null;
  pending_effective_week: string | null;
}

export interface SahadevaReviewResult {
  user_id: string;
  decision: SahadevaReviewDecision;
  effective_from_week: string;
  scheduled_at: string;
}

export interface ActivationResult {
  effective_week: string;
  scoring_rule_versions_activated: number;
  standard_versions_activated: number;
  category_configs_activated: number;
  organization_setting_versions_activated: number;
}

export interface CategoryHistoryEntryPublic {
  id: string;
  previous_category_code: string | null;
  new_category_code: string;
  effective_from_week: string;
  change_source: string;
  reason: string;
  changed_by_id: string | null;
}

export interface HistoricalCategoryHistoryPublic {
  devotee_user_id: string;
  current_category_code: string;
  current_academic_year: number | null;
  history: CategoryHistoryEntryPublic[];
}

export interface HistoricalCategoryCorrectionResult {
  devotee_user_id: string;
  correction_batch_id: string;
  effective_from_week: string;
  effective_until_exclusive: string | null;
  previous_category_code: string;
  corrected_category_code: string;
  next_transition_category_code: string | null;
  history_rows_removed_as_redundant: number;
  affected_daily_cards: number;
  affected_weekly_evaluations: number;
  current_profile_updated: boolean;
  current_category_code: string;
  current_academic_year: number | null;
}

export interface HistoricalCardCorrectionResult {
  devotee_user_id: string;
  card_date: string;
  card: DailyCardPublic;
  weekly_evaluation_recalculated: boolean;
  weekly_evaluation?: WeeklyEvaluationPublic | null;
}
