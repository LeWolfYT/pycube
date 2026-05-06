#version 330

in vec3 vertexPosition;
in vec3 vertexNormal;
in vec2 vertexTexCoord;

uniform mat4 mvp;
uniform mat4 matModel;

out vec3 fragNormal;
out vec3 fragPos;
out vec2 fragTexCoord;

void main()
{
    vec4 worldPos = matModel * vec4(vertexPosition, 1.0);
    fragPos = vec3(worldPos);
    fragNormal = mat3(transpose(inverse(matModel))) * vertexNormal;
    fragTexCoord = vertexTexCoord;
    gl_Position = mvp * vec4(vertexPosition, 1.0);
}
