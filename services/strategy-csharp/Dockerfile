FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY src/*.csproj ./
RUN dotnet restore

COPY src/. ./
RUN dotnet publish -c Release -o /app/publish

# Use ASP.NET runtime for WebApplication
FROM mcr.microsoft.com/dotnet/aspnet:10.0
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/publish .

ENTRYPOINT ["dotnet", "StrategyEngine.dll"]
