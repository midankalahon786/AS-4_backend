pipeline {
    agent any

    environment {
        IMAGE = "192.168.42.141:5000/aabhar-backend"
        TAG = "${env.BUILD_NUMBER}"
        DOCKER_BUILDKIT = "1"
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
        timestamps()
    }

    stages {
        stage('Checkout') {
            when {
                branch 'local-dev'
            }
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            when {
                branch 'local-dev'
            }
            steps {
                sh '''
                    docker build \
                        -t $IMAGE:$TAG \
                        -t $IMAGE:latest \
                        .
                '''
            }
        }

        stage('Push Docker Image') {
            when {
                branch 'local-dev'
            }
            steps {
                sh '''
                    docker push $IMAGE:$TAG
                    docker push $IMAGE:latest
                '''
            }
        }
    }

    post {
        success {
            echo "Successfully built and pushed ${IMAGE}:${TAG}"
        }

        failure {
            echo "Aabhar backend image build or push failed."
        }
    }
}
