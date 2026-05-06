#version 330

in vec3 fragNormal;
in vec3 fragPos;
in vec2 fragTexCoord;

uniform sampler2D texture0;
uniform vec3 lightPos;
uniform vec3 viewPos;
uniform vec3 lightColor;

out vec4 fragColor;

void main()
{
    vec3 norm = normalize(fragNormal);
    vec3 lightDir = normalize(lightPos - fragPos);
    vec3 viewDir = normalize(viewPos - fragPos);
    vec3 halfwayDir = normalize(lightDir + viewDir);

    vec3 texColor = texture(texture0, fragTexCoord).rgb;

    // Lighting
    vec3 ambient = 0.1 * texColor;
    float diff = max(dot(norm, lightDir), 0.0);
    vec3 diffuse = diff * texColor;

    float spec = pow(max(dot(norm, halfwayDir), 0.0), 64.0);
    vec3 specular = spec * lightColor;

    vec3 result = ambient + diffuse + specular;

    fragColor = vec4(result, 1.0);
}
