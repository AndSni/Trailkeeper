package com.asnidev.trailkeeper.network

import com.google.gson.annotations.SerializedName

data class RegisterRequest(
    val email: String,
    val name: String,
    val password: String,
    @SerializedName("organisation_name") val organisationName: String,
)

data class LoginRequest(val email: String, val password: String)

data class RefreshRequest(@SerializedName("refresh_token") val refreshToken: String)

data class TokenPair(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer",
)

data class MembershipDto(
    @SerializedName("organisation_id") val organisationId: String,
    @SerializedName("org_role") val orgRole: String,
)

data class UserDto(
    val id: String,
    val email: String,
    val name: String,
    @SerializedName("is_active") val isActive: Boolean,
)

data class MeResponse(val user: UserDto, val memberships: List<MembershipDto>)

data class ProjectDto(
    val id: String,
    @SerializedName("organisation_id") val organisationId: String,
    val name: String,
    val description: String,
    val activity: String,
    val status: String,
)

data class CreateProjectRequest(
    val name: String,
    val description: String = "",
    val activity: String = "mtb",
)
