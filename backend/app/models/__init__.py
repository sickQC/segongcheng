from app.models.assessment import CourseQuiz, QuizAttempt
from app.models.diagnosis_report import DiagnosisReport
from app.models.foundation import Chapter, Course, CourseMember, KnowledgePoint, User, UserSession
from app.models.learning_session import LearningSession, LearningTurn
from app.models.legacy import Diagnosis, LearningEvent, ModelTrace
from app.models.practice import PracticeExercise, PracticeSubmission
from app.models.profile import MasteryProfile, ProfileApplication, ProfileSnapshot
from app.models.recommendation import KnowledgeEdge, Recommendation, RecommendationFeedback
from app.models.resources import CourseResource, ResourceChunk, ResourceVersion, VideoCompletion

__all__ = [
    "Chapter",
    "Course",
    "CourseMember",
    "KnowledgePoint",
    "User",
    "UserSession",
    "Diagnosis",
    "LearningEvent",
    "ModelTrace",
    "PracticeExercise",
    "PracticeSubmission",
    "CourseQuiz",
    "QuizAttempt",
    "DiagnosisReport",
    "LearningSession",
    "LearningTurn",
    "MasteryProfile",
    "ProfileApplication",
    "ProfileSnapshot",
    "KnowledgeEdge",
    "Recommendation",
    "RecommendationFeedback",
    "CourseResource",
    "ResourceVersion",
    "ResourceChunk",
    "VideoCompletion",
]
